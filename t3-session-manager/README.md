# T3 Code Session Manager

[English](#english) | [中文](#中文)

## English

T3 Code Session Manager is the [Session Manager](../session-manager/) for [T3 Code](https://t3.codes). T3 Code runs Claude Code, Codex, and other coding agents side by side in one app. This skill makes one T3 Code thread the manager of all the others, whichever agent they use. You talk only to the manager. It shows you the thread that finished first and has waited longest, passes your reply into that thread word for word, and then shows the next one.

Works on **Windows**, **macOS**, and **Linux**. It needs Python 3 and nothing else.

### Requirements

- The T3 Code desktop app running on this computer, with Claude Code set up as one of its agents. The manager is itself a Claude thread.
- The `t3` command. T3 Code installs it in `~/.t3/bin`, and the helper looks there first.
- Python 3. On Windows, install it from python.org. On macOS, run `xcode-select --install` if `python3` is missing.

### Install

Clone this repository once, then link the skill folder into `~/.claude/skills`, so that a later `git pull` updates it. T3 Code's Claude threads read skills from that folder.

macOS or Linux:

```bash
git clone https://github.com/xinliulab/vibe-coding-tools.git ~/vibe-coding-tools
mkdir -p ~/.claude/skills
ln -s ~/vibe-coding-tools/t3-session-manager ~/.claude/skills/t3-session-manager
```

Windows (PowerShell):

```powershell
git clone https://github.com/xinliulab/vibe-coding-tools.git "$HOME\vibe-coding-tools"
New-Item -ItemType Junction -Path "$HOME\.claude\skills\t3-session-manager" -Target "$HOME\vibe-coding-tools\t3-session-manager"
```

### Use

1. In T3 Code, start a new Claude thread in any project and type `/t3-session-manager`.
2. It shows the first waiting thread: what it finished, or what it is asking you. Claude and Codex threads are in the same queue.
3. Reply as if you were in that thread. The manager relays your words unchanged and shows the next thread.

You can also say `next`, `skip`, `never show it`, or `full` (to see its whole last reply). You can ask it to tell you whenever a thread finishes. To go to a thread yourself, click it in the T3 Code sidebar.

### Tips and limits

- The manager relays only what you type in its own chat. It refuses messages that reach it in any other way, such as through `t3 thread send`.
- Approvals can only be answered inside their own thread. The manager tells you which thread to open.
- These threads are left out: threads you settled or snoozed in T3 Code, and history that T3 Code imported from other apps but never ran itself.
- Each computer runs its own manager, and it sees only the threads on that computer.
- To find your projects, the helper reads T3 Code's local database (read-only). A T3 Code update that changes this database could require an update here.
- State (which threads you skipped or hid) lives in `~/.claude/t3-session-manager/state.json`.

### Files

| File | Purpose |
|---|---|
| `SKILL.md` | The instructions Claude follows as the manager |
| `t3queue.py` | Queue helper: builds the queue, keeps the skip and hide lists, relays a message, and can watch for finished threads (standard library only) |

## 中文

T3 Code Session Manager 是给 [T3 Code](https://t3.codes) 用的 [Session Manager](../session-manager/)。T3 Code 把 Claude Code、Codex 等写代码的 agent 放在一个 app 里一起用。这个技能让其中一个 T3 Code 对话当"管理员"，管理其他所有对话，不管它们用的是哪家 agent。你只跟管理员说话：它按完成的先后，把等得最久的那个对话拿给你看；你回什么，它就原话转给那个对话，然后给你看下一个。

支持 **Windows**、**macOS** 和 **Linux**，只需要 Python 3。

### 需要

- 本机运行着 T3 Code 桌面 app，并且接好了 Claude Code。管理员本身是一个 Claude 对话。
- `t3` 命令。T3 Code 会把它装在 `~/.t3/bin`，工具会先去那里找。
- Python 3。Windows 从 python.org 装；macOS 上如果没有 `python3`，运行 `xcode-select --install`。

### 安装

把这个仓库 clone 一次，再把技能文件夹链接到 `~/.claude/skills`，以后 `git pull` 就会自动更新。T3 Code 里的 Claude 对话会从这个文件夹读技能。命令见上面英文部分：macOS 和 Linux 用 `ln -s`，Windows 用 `New-Item -ItemType Junction`。

### 用法

1. 在 T3 Code 里，随便选一个项目，新开一个 Claude 对话，输入 `/t3-session-manager`。
2. 它给你看第一个在等的对话：做完了什么，或者在问你什么。Claude 和 Codex 的对话排在同一个队列里。
3. 像在那个对话里一样回复，管理员原话转过去，再给你看下一个。

还可以说 `下一个`、`跳过`、`以后别显示它`、`全文`（看它上一条的完整回复），或者让它"哪个做完了就告诉我"。想自己去某个对话，在 T3 Code 左边栏点它就行。

### 注意

- 管理员只转发你在它自己对话框里打的字。用别的办法塞给它的消息（比如 `t3 thread send`），它会拒绝转发。
- 权限确认只能在那个对话里点，管理员会告诉你该去哪个对话。
- 以下对话不会出现在队列里：你在 T3 Code 里标为完成（settle）或者稍后提醒（snooze）的对话，以及 T3 Code 从别的 app 导入、但从没在 T3 Code 里跑过的历史对话。
- 每台电脑各开一个管理员，它只能看到本机的对话。
- 为了找到你的项目，工具会只读地读取 T3 Code 的本地数据库。如果 T3 Code 升级后改了这个数据库，这里可能要跟着更新。
- 跳过、隐藏了哪些对话，记在 `~/.claude/t3-session-manager/state.json`。
