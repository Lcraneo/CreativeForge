from gimport.adapters.cocos_adapter import CocosAdapter
from gimport.adapters.unity_adapter import UnityAdapter
from gimport.adapters.godot_adapter import GodotAdapter

ENGINE_ADAPTERS = {
    "cocos": CocosAdapter,
    "unity": UnityAdapter,
    "godot": GodotAdapter
}
