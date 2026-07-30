# Chapter Parser Scripts

v0.20 AI章节划分智能体会先执行本目录中的 `*.py` 脚本。脚本从 stdin 读取完整 txt 小说，并输出：

```json
{"chapters":[{"chapter_id":"chapter-0001","title":"章节标题","body":"章节正文"}]}
```

运行时由智能体生成的脚本命名为 `agent_generated_*.py`，会保存在本目录供后续相同格式小说复用。
