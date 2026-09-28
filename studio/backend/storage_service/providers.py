"""六厂商对象存储的 S3 兼容统一实现（boto3 驱动）。

方案确认：阿里云 OSS / 腾讯云 COS / 七牛云 Kodo / 华为云 OBS / 火山引擎 TOS /
百度智能云 BOS 全部通过各家官方提供的 S3 兼容端点接入，单一 boto3 依赖覆盖
六家（参考 Windup 的七牛 SDK 用法 + COS 手写签名思路，统一收敛到 S3 协议）。

每个厂商一个 preset：S3 兼容端点模板 + 常用地域 + 寻址风格（virtual-host /
path）。自定义 Endpoint 优先于模板。
"""

from __future__ import annotations

import time

from .interface import (
    StorageAuthError,
    StorageConfig,
    StorageConfigError,
    StorageNotFoundError,
    StorageTimeoutError,
    StoredObject,
    redact,
)

__all__ = ["PROVIDER_PRESETS", "S3CompatProvider", "create_provider"]


# ── 厂商预设 ────────────────────────────────────────────────────────────────
# endpoint 模板里的 {region} 会被替换；addressing 决定 boto3 的桶寻址风格：
#   virtual: https://<bucket>.<host>/key  （OSS/COS/OBS/TOS/BOS 推荐）
#   path:    https://<host>/<bucket>/key  （七牛 Kodo 兼容性更稳）

PROVIDER_PRESETS: dict[str, dict] = {
    "oss": {
        "id": "oss",
        "label": "阿里云 OSS",
        "endpoint_template": "https://oss-{region}.aliyuncs.com",
        "addressing": "virtual",
        "regions": ["cn-hangzhou", "cn-beijing", "cn-shanghai", "cn-guangzhou", "cn-shenzhen", "cn-hongkong"],
        "credential_hint": "AccessKeyId / AccessKeySecret（RAM 控制台创建）",
    },
    "cos": {
        "id": "cos",
        "label": "腾讯云 COS",
        "endpoint_template": "https://cos.{region}.myqcloud.com",
        "addressing": "virtual",
        "regions": ["ap-guangzhou", "ap-shanghai", "ap-beijing", "ap-nanjing", "ap-chengdu", "ap-hongkong"],
        "credential_hint": "SecretId / SecretKey（访问管理 CAM 创建）",
    },
    "kodo": {
        "id": "kodo",
        "label": "七牛云 Kodo",
        "endpoint_template": "https://s3.{region}.qiniucs.com",
        "addressing": "path",
        "regions": ["cn-east-1", "cn-north-1", "cn-south-1", "us-west-1", "ap-southeast-1"],
        "credential_hint": "AccessKey / SecretKey（七牛控制台「密钥管理」）",
    },
    "obs": {
        "id": "obs",
        "label": "华为云 OBS",
        "endpoint_template": "https://obs.{region}.myhuaweicloud.com",
        "addressing": "virtual",
        "regions": ["cn-north-4", "cn-east-3", "cn-south-1", "cn-north-9", "ap-southeast-1"],
        "credential_hint": "Access Key Id / Secret Access Key（我的凭证-访问密钥）",
    },
    "tos": {
        "id": "tos",
        "label": "火山引擎 TOS",
        "endpoint_template": "https://tos-s3-{region}.volces.com",
        "addressing": "virtual",
        "regions": ["cn-beijing", "cn-shanghai", "cn-guangzhou", "ap-southeast-1"],
        "credential_hint": "AccessKey / SecretKey（IAM 访问密钥）",
    },
    "bos": {
        "id": "bos",
        "label": "百度智能云 BOS",
        "endpoint_template": "https://s3.{region}.bcebos.com",
        "addressing": "virtual",
        "regions": ["bj", "bd", "su", "gz", "hkg"],
        "credential_hint": "Access Key ID / Secret Access Key（安全认证 BCC/AK）",
    },
}

DEFAULT_TIMEOUT = 30  # 单请求超时（秒）
DEFAULT_RETRIES = 3


def resolve_endpoint(config: StorageConfig) -> str:
    """自定义 Endpoint 优先；否则按厂商模板 + 地域生成。"""
    if config.endpoint:
        return config.endpoint.rstrip("/")
    preset = PROVIDER_PRESETS.get(config.provider)
    if not preset:
        raise StorageConfigError(f"未知对象存储厂商 {config.provider!r}；支持 {sorted(PROVIDER_PRESETS)}")
    if not config.region:
        raise StorageConfigError(f"{preset['label']} 需要填写地域 region")
    return preset["endpoint_template"].format(region=config.region)


class S3CompatProvider:
    """S3 兼容协议统一实现。构造零网络调用，首个请求才建客户端。"""

    def __init__(self, config: StorageConfig, *, timeout: int = DEFAULT_TIMEOUT):
        if not config.bucket:
            raise StorageConfigError("bucket 不能为空")
        if not config.access_key or not config.secret_key:
            raise StorageConfigError("缺少访问凭证（access_key / secret_key）")
        self._config = config
        self._timeout = timeout
        self._client = None

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from botocore.config import Config
            import boto3
        except ImportError as exc:  # pragma: no cover - 环境问题
            raise StorageConfigError(
                "缺少 boto3 依赖：pip install boto3（S3 兼容统一驱动）"
            ) from exc

        preset = PROVIDER_PRESETS.get(self._config.provider, {})
        addressing = preset.get("addressing", "virtual")
        endpoint = resolve_endpoint(self._config)
        # 凭证只从 StorageConfig 注入客户端，绝不写日志 / 异常文本
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self._config.access_key,
            aws_secret_access_key=self._config.secret_key,
            region_name=self._config.region or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": addressing},
                connect_timeout=self._timeout,
                read_timeout=self._timeout,
                retries={"max_attempts": DEFAULT_RETRIES, "mode": "adaptive"},
            ),
        )
        return self._client

    def _wrap(self, exc: Exception, action: str) -> Exception:
        """把 botocore 异常翻译进分级体系（文本过 redact，杜绝密钥外泄）。"""
        code = getattr(getattr(exc, "response", None), "get", lambda *_: None)("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
        name = type(exc).__name__
        message = redact(f"{action}: {exc}")
        if "AccessDenied" in str(code) or "SignatureDoesNotMatch" in str(code) or "InvalidAccessKeyId" in str(code) or "Unauthorized" in str(exc):
            return StorageAuthError(message)
        if "NoSuchKey" in str(code) or "NoSuchBucket" in str(code) or "404" in str(code):
            return StorageNotFoundError(message)
        if "Timeout" in name or "timeout" in str(exc).lower():
            return StorageTimeoutError(message)
        from botocore.exceptions import BotoCoreError, ClientError  # noqa: PLC0415

        if isinstance(exc, (BotoCoreError, ClientError)):
            return StorageError(message)
        return StorageError(message)

    @staticmethod
    def _to_object(item: dict) -> StoredObject:
        return StoredObject(
            key=str(item.get("Key", "")),
            size=int(item.get("Size", 0)),
            last_modified=str(item.get("LastModified", "")),
            etag=str(item.get("ETag", "")).strip('"'),
        )

    # ── StorageProvider 端口 ────────────────────────────────────────────────

    def upload(self, data: bytes, key: str, *, content_type: str = "application/octet-stream") -> StoredObject:
        client = self._ensure_client()
        try:
            client.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:  # noqa: BLE001 - 统一翻译
            raise self._wrap(exc, f"upload {key}") from exc
        return StoredObject(key=key, size=len(data), last_modified="", etag="")

    def download(self, key: str) -> bytes:
        client = self._ensure_client()
        try:
            response = client.get_object(Bucket=self._config.bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"download {key}") from exc

    def list(self, prefix: str = "", limit: int = 100) -> list[StoredObject]:
        client = self._ensure_client()
        try:
            response = client.list_objects_v2(
                Bucket=self._config.bucket, Prefix=prefix or "", MaxKeys=max(1, min(limit, 1000))
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"list {prefix!r}") from exc
        return [self._to_object(item) for item in response.get("Contents", [])]

    def delete(self, key: str) -> None:
        client = self._ensure_client()
        try:
            client.delete_object(Bucket=self._config.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"delete {key}") from exc

    def presign(self, key: str, expires: int = 3600) -> str:
        client = self._ensure_client()
        try:
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._config.bucket, "Key": key},
                ExpiresIn=max(60, min(int(expires), 7 * 24 * 3600)),
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"presign {key}") from exc

    def test(self) -> dict:
        """连通性测试：list max_keys=1。凭证错→AuthError；桶/网络问题分级返回。"""
        started = time.time()
        try:
            client = self._ensure_client()
            response = client.list_objects_v2(Bucket=self._config.bucket, MaxKeys=1)
            latency = int((time.time() - started) * 1000)
            return {
                "ok": True,
                "latency_ms": latency,
                "detail": f"Bucket 可达（列举成功，耗时 {latency}ms）",
            }
        except Exception as exc:  # noqa: BLE001
            wrapped = self._wrap(exc, "test")
            return {"ok": False, "latency_ms": int((time.time() - started) * 1000), "detail": str(wrapped)}

    # ── 分片扩展端口（transfer.MultipartCapable） ──────────────────────────

    def create_multipart_upload(self, key: str, *, content_type: str = "application/octet-stream") -> str:
        client = self._ensure_client()
        try:
            response = client.create_multipart_upload(
                Bucket=self._config.bucket, Key=key, ContentType=content_type)
            return str(response["UploadId"])
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"create_multipart_upload {key}") from exc

    def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str:
        client = self._ensure_client()
        try:
            response = client.upload_part(
                Bucket=self._config.bucket, Key=key, UploadId=upload_id,
                PartNumber=part_number, Body=data)
            return str(response["ETag"]).strip('"')
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"upload_part {key}#{part_number}") from exc

    def list_parts(self, key: str, upload_id: str) -> dict[int, str]:
        client = self._ensure_client()
        parts: dict[int, str] = {}
        token = None
        try:
            while True:
                kwargs = {"Bucket": self._config.bucket, "Key": key, "UploadId": upload_id}
                if token:
                    kwargs["PartNumberMarker"] = token
                response = client.list_parts(**kwargs)
                for item in response.get("Parts", []):
                    parts[int(item["PartNumber"])] = str(item["ETag"]).strip('"')
                if response.get("IsTruncated"):
                    token = response.get("NextPartNumberMarker")
                else:
                    break
            return parts
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"list_parts {key}") from exc

    def complete_multipart_upload(self, key: str, upload_id: str, parts: list[tuple[int, str]]) -> dict:
        client = self._ensure_client()
        try:
            response = client.complete_multipart_upload(
                Bucket=self._config.bucket, Key=key, UploadId=upload_id,
                MultipartUpload={"Parts": [
                    {"PartNumber": n, "ETag": etag} for n, etag in sorted(parts)
                ]})
            return {"key": key, "etag": str(response.get("ETag", "")).strip('"'),
                    "location": str(response.get("Location", ""))}
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"complete_multipart_upload {key}") from exc

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        client = self._ensure_client()
        try:
            client.abort_multipart_upload(
                Bucket=self._config.bucket, Key=key, UploadId=upload_id)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"abort_multipart_upload {key}") from exc


def create_provider(config: StorageConfig, *, timeout: int = DEFAULT_TIMEOUT) -> S3CompatProvider:
    """按配置创建 provider。厂商合法性在这里前置校验（构造即报错）。"""
    if config.provider not in PROVIDER_PRESETS:
        raise StorageConfigError(
            f"未知厂商 {config.provider!r}；支持 {sorted(PROVIDER_PRESETS)}"
        )
    return S3CompatProvider(config, timeout=timeout)
