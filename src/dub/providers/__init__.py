"""Cloud provider clients.

Each module wraps one external service. The stages in ../stages/ call
into these. Keeping them separate makes it easy to swap providers
(MiniMax -> Aliyun CosyVoice, DeepSeek -> Qwen-Max, etc.) without
touching stage logic.
"""
