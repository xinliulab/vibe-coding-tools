# T3 Code Session Manager

[English](#english) | [中文](#中文)

## English

T3 Code Session Manager is the [Session Manager](../session-manager/) for [T3 Code](https://t3.codes). T3 Code runs Claude Code, Codex, and other coding agents side by side in one app. This skill makes one T3 Code thread the manager of all the others, whichever agent they use. You talk only to the manager. It shows you the thread that finished first and has waited longest, passes your reply into that thread word for word, and then shows the next one.

It also covers your **other machines**. When you link other T3 Code machines to this one (**Settings → Labs → Linked environments**, then link them under **Settings → Environments**), their threads join the same queue, labeled with the machine's name. The manager reads and relays them through T3 Code's own agent tools.

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

You can also say `next`, `skip`, `never show it`, or `full` (to see its whole last reply). To go to a thread yourself, click it in the T3 Code sidebar.

**It reports on its own.** Whenever a thread on this computer or a linked one finishes, the manager wakes up and tells you which one finished and what it got done; you never have to ask. T3 Code does not wake one thread when another finishes, so the skill starts a small background watcher. The watcher follows the notification badge that the T3 desktop app writes to its local log, and messages the manager when the badge changes. It costs no model tokens, sends nothing anywhere else, and stops when the manager thread is archived or deleted.

- T3's **Settings → Notifications** must not be **Off**, because the badge only moves when notifications are on. To keep the screen quiet, turn off banners and sounds for T3 Code in the operating system's notification settings (on Windows: Settings → System → Notifications → T3 Code → Show notification banners off).
- T3 raises the badge only while you are not looking at T3, so reports arrive when your attention is elsewhere.
- Work the manager starts itself runs as delegated tasks, and T3 wakes the manager directly when those end.

### Tips and limits

- The manager relays only what you type in its own chat. It refuses messages that reach it in any other way, such as through `t3 thread send`.
- Approvals can only be answered inside their own thread. The manager tells you which thread to open.
- These threads are left out: threads you settled or snoozed in T3 Code, and history that T3 Code imported from other apps but never ran itself.
- The manager sees the threads on its own computer and on the machines linked to it. A machine that is linked but not reachable right now is skipped until it is.
- One manager per computer gets the automatic reports. Starting a new manager moves the watcher to it.
- The watcher relies on a line in the T3 desktop app's log. A T3 Code update that changes this log could require an update here.
- To find your projects, the helper reads T3 Code's local database (read-only). A T3 Code update that changes this database could require an update here.
- State (which threads you skipped or hid) lives in `~/.claude/t3-session-manager/state.json`.

### Files

| File | Purpose |
|---|---|
| `SKILL.md` | The instructions Claude follows as the manager |
| `t3queue.py` | Queue helper: builds the queue, keeps the skip and hide lists, relays a message, and runs the wake watcher (standard library only) |

## 中文

T3 Code Session Manager 是给 [T3 Code](https://t3.codes) 用的 [Session Manager](../session-manager/)。T3 Code 把 Claude Code、Codex 等写代码的 agent 放在一个 app 里一起用。这个技能让其中一个 T3 Code 对话当"管理员"，管理其他所有对话，不管它们用的是哪家 agent。你只跟管理员说话：它按完成的先后，把等得最久的那个对话拿给你看；你回什么，它就原话转给那个对话，然后给你看下一个。

它也能管你的**其他电脑**。把别的 T3 Code 电脑和这台连起来以后（先打开 **Settings → Labs → Linked environments**，再到 **Settings → Environments** 里连接），那些电脑上的对话也会排进同一个队列，前面标着是哪台电脑。管理员用 T3 Code 自带的 agent 工具去读那些对话、转发你的话。

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

还可以说 `下一个`、`跳过`、`以后别显示它`、`全文`（看它上一条的完整回复）。想自己去某个对话，在 T3 Code 左边栏点它就行。

**它会主动汇报。**本机或连好的其他电脑上，只要有对话做完，管理员就会自己醒来，告诉你哪个做完了、做到了什么程度，不用你问。T3 Code 本身不会因为一个对话做完就叫醒另一个对话，所以这个技能会在后台开一个很小的程序：T3 桌面 app 每次更新提醒数字时会在本机日志里记一笔，这个小程序就盯着这一笔，一出现就给管理员发一条消息。它不耗模型额度，不往外发任何东西，管理员对话归档或删除后会自己停。

- T3 的 **Settings → Notifications** 不能设成 **Off**，否则提醒数字不会变。不想让屏幕上弹东西的话，在系统的通知设置里把 T3 Code 的横幅和声音关掉（Windows：设置 → 系统 → 通知 → T3 Code → 关掉"显示通知横幅"）。
- 你正看着 T3 的时候，T3 不会更新提醒数字，所以汇报会在你看别处的时候到。
- 管理员自己开的活会用"委派"方式开，这些活一结束，T3 会直接叫醒管理员。

### 注意

- 管理员只转发你在它自己对话框里打的字。用别的办法塞给它的消息（比如 `t3 thread send`），它会拒绝转发。
- 权限确认只能在那个对话里点，管理员会告诉你该去哪个对话。
- 以下对话不会出现在队列里：你在 T3 Code 里标为完成（settle）或者稍后提醒（snooze）的对话，以及 T3 Code 从别的 app 导入、但从没在 T3 Code 里跑过的历史对话。
- 管理员能看到它所在电脑上的对话，以及和这台电脑连好的其他电脑上的对话。连好了但暂时连不上的电脑会先跳过，等能连上了再算进来。
- 每台电脑上只有一个管理员能收到自动汇报。新开一个管理员，后台小程序就会转到新的那个。
- 后台小程序靠的是 T3 桌面 app 日志里的一行记录。如果 T3 Code 升级后改了日志格式，这里可能要跟着更新。
- 为了找到你的项目，工具会只读地读取 T3 Code 的本地数据库。如果 T3 Code 升级后改了这个数据库，这里可能要跟着更新。
- 跳过、隐藏了哪些对话，记在 `~/.claude/t3-session-manager/state.json`。
