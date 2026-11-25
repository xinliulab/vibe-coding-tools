# Session Manager

[English](#english) | [中文](#中文)

## English

Session Manager is a Claude Code skill for people who run many Claude Desktop sessions at once. One session becomes the manager: you talk only to it. It shows you the session that finished first and has waited longest, passes your reply into that session word for word, then shows the next one. You stop clicking from session to session.

Works on **Windows** (PowerShell, built in) and **macOS** (Python 3).

### Requirements

- The Claude Desktop app (Code tab), with several local sessions running.
- Windows: nothing else.
- macOS: `python3`. If it is missing, run `xcode-select --install`.
- Optional: the switchboard plugin. With it, the manager can also tell "asking you" and "error" apart from "done".

### Install

Clone this repository once, then link the skill folder into `~/.claude/skills`, so a later `git pull` updates it.

macOS:

```bash
git clone https://github.com/xinliulab/vibe-coding-tools.git ~/vibe-coding-tools
mkdir -p ~/.claude/skills
ln -s ~/vibe-coding-tools/session-manager ~/.claude/skills/session-manager
```

Windows (PowerShell):

```powershell
git clone https://github.com/xinliulab/vibe-coding-tools.git "$HOME\vibe-coding-tools"
New-Item -ItemType Junction -Path "$HOME\.claude\skills\session-manager" -Target "$HOME\vibe-coding-tools\session-manager"
```

### Use

1. Start a new session in the Claude Desktop app and type `/session-manager`.
2. It shows the first waiting session: what it finished, or what it is asking you.
3. Reply as if you were in that session. The manager relays your words unchanged and shows the next session.

Other things you can say: `next`, `skip`, `never show it`, `full` (its whole last reply), `open it` (a link to jump over), or ask it to tell you whenever a session finishes.

### Tips and limits

- Give the manager the **same permission mode** as your other sessions. When the modes differ, the app holds relayed messages until you release them in the target session.
- Each computer runs its own manager. It sees only the sessions on that computer.
- Permission prompts can only be answered inside their own session; the manager gives you a link.
- State (which sessions you skipped or hid) lives in `~/.claude/session-manager/state.json`.

### Files

| File | Purpose |
|---|---|
| `SKILL.md` | The instructions Claude follows as the manager |
| `queue.ps1` | Queue helper for Windows |
| `queue.py` | Queue helper for macOS and Linux (standard library only) |

## 中文

Session Manager 是一个 Claude Code 技能，适合同时开很多个 Claude Desktop 会话的人。让其中一个会话当"管理员"，你只跟它说话：它按完成的先后，把等得最久的那个会话拿给你看；你回什么，它就原话转给那个会话，然后给你看下一个。不用再一个个点来点去。

支持 **Windows**（用系统自带的 PowerShell）和 **macOS**（用 Python 3）。

### 需要

- Claude Desktop app（Code 页），本机开着几个会话。
- Windows：不需要别的。
- macOS：需要 `python3`。没有的话运行 `xcode-select --install`。
- 可选：switchboard 插件。装了以后，管理员还能分清"在问你""出错了"和"做完了"。

### 安装

把这个仓库 clone 一次，再把技能文件夹链接到 `~/.claude/skills`，以后 `git pull` 就自动更新。命令见上面英文部分（macOS 用 `ln -s`，Windows 用 `New-Item -ItemType Junction`）。

### 用法

1. 在 Claude Desktop app 里新开一个会话，输入 `/session-manager`。
2. 它给你看第一个在等的会话：做完了什么，或者在问你什么。
3. 像在那个会话里一样回复，管理员原话转过去，再给你看下一个。

还可以说：`下一个`、`跳过`、`以后别显示它`、`全文`（它上一条的完整回复）、`去看`（给你一个跳过去的链接），或者让它"哪个做完了就告诉我"。

### 注意

- 管理员要和其他会话用**同一个权限模式**。模式不一样时，app 会把转过去的消息扣住，要你到那个会话里放行。
- 每台电脑各开一个管理员，它只能看到本机的会话。
- 权限确认只能在那个会话里点，管理员会给你链接。
- 跳过、隐藏了哪些会话，记在 `~/.claude/session-manager/state.json`。
