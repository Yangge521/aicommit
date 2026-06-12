# aicommit — 推送到 GitHub 的操作指南

## 当前状态

- ✅ 项目代码完整，14 项测试全部通过
- ✅ Git 仓库已初始化，2 个 commit 已就绪
- ❌ 当前网络环境无法访问 `api.github.com`，`gh repo create` 失败

## 推送步骤

### 方法一：手动创建仓库后推送（推荐）

1. 浏览器打开 https://github.com/new
2. Repository name 填 `aicommit`
3. Description 填 `AI writes your git commit messages. You ship code.`
4. 选择 **Public**
5. **不要** 勾选 "Add a README file" / "Add .gitignore" / "Choose a license"
6. 点击 "Create repository"
7. 在终端执行以下命令：

```powershell
cd C:\Users\25577\.qclaw\workspace-agent-0921f0f0\aicommit
git remote add origin https://github.com/Ghy/aicommit.git
git push -u origin master
```

### 方法二：等网络恢复后用 gh CLI（一行命令）

```powershell
cd C:\Users\25577\.qclaw\workspace-agent-0921f0f0\aicommit
gh repo create Ghy/aicommit --public --description "AI writes your git commit messages. You ship code." --source . --remote origin --push
```

## 推送后发布到 PyPI

```bash
# 打 tag
git tag v1.1.0
git push origin v1.1.0

# GitHub Actions 会自动发布到 PyPI
# 或者手动发布：
pip install build twine
python -m build
twine upload dist/*
```

## 项目文件列表

```
aicommit/
├── README.md                          # 中英双语文档
├── LICENSE                            # MIT
├── pyproject.toml                     # 包配置 v1.1.0
├── .gitignore
├── .github/workflows/publish.yml      # PyPI 自动发布
├── aicommit/
│   ├── __init__.py                    # 版本号
│   ├── __main__.py                    # python -m 入口
│   ├── cli.py                         # Click CLI 主入口 (~280行)
│   ├── git_utils.py                   # Git 操作+智能分析 (~240行)
│   ├── ai.py                          # AI API 调用 (~130行)
│   ├── config.py                      # 配置管理+向导 (~150行)
│   ├── prompts.py                     # 4种风格的Prompt (~110行)
│   └── render.py                      # Rich终端渲染 (~140行)
└── tests/
    └── test_basic.py                  # 14项测试
```
