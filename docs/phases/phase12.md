进入 Phase 12：真实 AI 能力接入层设计与实现
这一阶段开始把 Phase 11 的 Agent 骨架连接到真实 AI 能力。
Phase 1 已经确定：
CreativeAsset 是整个系统的数据协议，所有生成、处理、导入模块最终都需要转换为统一资产对象。
同时：
● PReCon
● FAlign
● GImport
都通过统一 AssetProcessor 接口处理资产。
外部能力：
● Holonic
● Windup
● Cocos
● Unity
通过 Adapter 接入。
所以 Phase 12 不直接把 API 写死，而是实现：
External AI

↓

Adapter

↓

CreativeAsset

↓

Agent Pipeline


Phase 12 总目标
完成真实链路：
用户 Prompt

↓

CreativeForge Agent

↓

Windup Adapter

↓

AI生成角色图片

↓

AssetStruct Engine

↓

CreativeAsset

↓

数据库保存


一、Phase 12 架构
                    User


                     |

                     ▼


              Agent Planner


                     |

                     ▼


              Tool Router


                     |

        ----------------------------


        Generate Tool


              |

              ▼


        Windup Adapter


              |

              ▼


        Generated Asset


              |

              ▼


        AssetStruct Tool


              |

              ▼


        CreativeAsset v1


              |

              ▼


        PostgreSQL


二、新增目录结构
在 Phase 11 基础上增加：
backend/


├── adapters/


│
├── windup/


│   ├── client.py

│   ├── mapper.py

│   └── adapter.py


├── holonic/


│
│   └── adapter.py



├── engines/


│
├── asset_struct/


│
│   ├── analyzer.py

│   ├── segmenter.py

│   └── processor.py


├── models/


│
└── creative_asset.py


├── tools/


│
├── generate_tool.py

├── struct_tool.py

└── dna_tool.py


三、Windup Adapter 设计
不要：
直接调用API
这样后期无法替换。
采用：
Windup

↓

WindupAdapter

↓

CreativeAsset


四、Adapter 接口
adapters/base.py
from abc import ABC, abstractmethod



class AssetAdapter(ABC):


    name:str


    @abstractmethod
    async def generate(
        self,
        request:dict
    ):
        pass



    @abstractmethod
    async def convert(
        self,
        raw_asset:dict
    ):
        pass


五、Windup Client
负责外部通信。
windup/client.py
import httpx



class WindupClient:


    def __init__(
        self,
        api_key:str,
        base_url:str
    ):

        self.api_key=api_key
        self.base_url=base_url



    async def generate(
        self,
        prompt:str
    ):


        async with httpx.AsyncClient() as client:


            response = await client.post(

                self.base_url + "/generate",

                headers={
                    "Authorization":
                    f"Bearer {self.api_key}"
                },


                json={
                    "prompt":prompt
                }

            )


            response.raise_for_status()


            return response.json()


六、Windup Mapper
作用：
外部返回：
{
image_url:
"xxx",

style:
"anime"

}
转换：
CreativeAsset。

windup/mapper.py
from datetime import datetime



def map_to_asset(
    data:dict
):


    return {


        "identity":{

            "name":
            "generated_character"

        },


        "source":{

            "provider":
            "windup"

        },


        "content":{

            "image":
            data["image_url"]

        },


        "style":{

            "name":
            data.get(
                "style",
                "unknown"
            )

        },


        "version":{

            "created":
            datetime.utcnow().isoformat()

        }


    }


七、Windup Adapter
windup/adapter.py
from app.adapters.base import AssetAdapter

from .client import WindupClient

from .mapper import map_to_asset



class WindupAdapter(
    AssetAdapter
):


    name="windup"



    def __init__(
        self,
        client:WindupClient
    ):

        self.client=client



    async def generate(
        self,
        request
    ):


        result = await self.client.generate(

            request["prompt"]

        )


        return map_to_asset(
            result
        )


八、注册 Adapter
新增：
adapter_registry={}
adapters/registry.py
from app.adapters.windup.adapter import WindupAdapter



class AdapterRegistry:


    def __init__(self):

        self.adapters={}



    def register(
        self,
        adapter
    ):

        self.adapters[
            adapter.name
        ]=adapter



    def get(
        self,
        name
    ):

        return self.adapters.get(name)



registry=AdapterRegistry()


九、Generate Tool 升级
之前：
模拟：
generated_character.png
现在：
调用：
Windup。

tools/generate_tool.py
from app.tools.base import BaseTool

from app.adapters.registry import registry



class GenerateTool(
    BaseTool
):


    name="generate_asset"



    async def run(
        self,
        params
    ):


        adapter = registry.get(
            "windup"
        )


        asset = await adapter.generate(

            {
                "prompt":
                params["goal"]
            }

        )


        return asset


十、AssetStruct Engine 开始实现
目标：
输入：
角色图片
输出：
body

weapon

effect

metadata

第一版不训练模型。
采用：
组合：
Vision LLM

+

SAM2

架构：
Image


 |

 ▼


Vision Analyzer


 |

 ▼


Semantic Parts


 |

 ▼


SAM2


 |

 ▼


Layers


十一、AssetStruct Processor
engines/asset_struct/processor.py
class AssetStructProcessor:


    name="asset_struct"



    async def process(
        self,
        asset
    ):


        image = asset["content"]["image"]


        result={


            "layers":[


                {

                "name":
                "body",

                "source":
                image


                }


            ]

        }


        asset["content"]["layers"]=result


        return asset


十二、Struct Tool
from app.tools.base import BaseTool


class StructTool(
    BaseTool
):


    name="structure_asset"



    async def run(
        self,
        params
    ):


        processor = AssetStructProcessor()


        return await processor.process(
            params["asset"]
        )


十三、升级 Agent Pipeline
现在：
用户：
生成机械猫战士
Planner：
生成任务：
{
tasks:[

"generate_asset",

"structure_asset",

"create_dna",

"export_asset"

]

}


执行：
generate_asset

↓

Windup Adapter


↓

CreativeAsset


↓

structure_asset


↓

AssetStruct


↓

DNA


↓

Export

