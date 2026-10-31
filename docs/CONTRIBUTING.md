# 贡献指引 (CONTRIBUTING)

感谢您对本项目的关注！任何形式的贡献（代码、文档、Bug 反馈、功能建议）都非常欢迎。

## 行为准则

- 保持友善、专业，尊重他人。
- 在讨论中提供建设性意见，聚焦问题本身。

## 如何报告 Bug

1. 先在 [Issues](https://github.com/Pzt1212/study-assistant/issues) 中搜索是否已有相同问题。
2. 若无，新建 Issue，请包含：
   - 问题描述（发生了什么、期望是什么）
   - 复现步骤
   - 运行环境（操作系统、Python 版本、浏览器）
   - 错误日志（若有）

## 如何提交代码

1. **Fork** 本仓库到你的账号。
2. 克隆到本地并创建特性分支：

```bash
git clone https://github.com/Pzt1212/study-assistant.git
cd study-assistant
git checkout -b feature/your-feature-name
```

3. 开发与自测：
   - 保持代码风格与现有代码一致（PEP8、中文注释、函数命名清晰）
   - 每个功能模块独立成文件（蓝图），不要堆在单个文件里
   - 新增依赖时同步更新 `requirements.txt` 并说明用途
   - 运行现有测试：`python -m unittest discover -s tests -v`
4. 提交与推送：

```bash
git add .
git commit -m "feat: 添加 xxx 功能"   # 提交信息建议参考 CHANGELOG.md 风格
git push origin feature/your-feature-name
```

5. 提交 **Pull Request**，在描述中说明改动内容与测试情况。

## 开发环境

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py              # 启动开发服务器（debug 模式）
```

## 代码结构约定

```
blueprints/   # 每个功能一个蓝图文件，路由 + 表单处理
models.py     # 数据访问层，所有 SQL 集中于此，路由不写 SQL
services/     # 可复用的业务服务（OCR、文本提取、音频生成）
templates/    # Jinja2 模板，页面级
static/       # CSS / JS / 音乐资源
docs/         # 文档（SCHEMA / ROUTES / 截图）
```

## 新增功能建议步骤

1. 在 `models.py` 增加数据访问函数（如需新表，更新 `db.py` 的 `SCHEMA`）。
2. 在 `blueprints/` 新建蓝图文件（或扩展现有蓝图）。
3. 在 `app.py` 注册蓝图。
4. 编写模板与静态资源。
5. 补充文档（`README.md`、`docs/ROUTES.md`）与测试。
6. 更新 `CHANGELOG.md`。

## 发布新版本

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)，发布时：
1. 更新 `CHANGELOG.md`。
2. 打 tag：`git tag v1.0.0 && git push --tags`。

再次感谢您的贡献！
