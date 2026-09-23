def map_generation(result):

    return {
        "source": {
            "source_type": "ai_generation",
            "provider": "windup",
            "prompt": result.get("prompt")
        }
    }
