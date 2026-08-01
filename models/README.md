# models

本目录只放本地模型说明或 gitignored symlink，不提交大型模型权重。

默认 Qwen3-TTS 模型路径由 `SHUYI_MODEL_DIR` 配置，容器默认使用 `/models`，本地开发建议使用仓库外的持久目录。

如果后续需要在本目录放 symlink，请确认 `.gitignore` 不会把权重文件提交进仓库。
