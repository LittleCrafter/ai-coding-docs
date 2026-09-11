> ## Documentation Index
> Fetch the complete documentation index at: https://code.claude.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Explore the context window

> An interactive simulation of how Claude Code's context window fills during a session. See what loads automatically, what each file read costs, and when rules and hooks fire.

## Session timeline

Each row is one step of a simulated session, in the order it happens. Token counts are representative, and the context window they fill holds 200,000 tokens.

| What enters context | Loaded by | Tokens | In your terminal | What it is |
| ------------------- | --------- | ------ | ---------------- | ---------- |
| System prompt | Auto-loaded | 4,200 | Invisible in your terminal | Core instructions for behavior, tool use, and response formatting. Always loaded first. You never see it. |
| Auto memory (MEMORY.md) | Auto-loaded | 680 | Invisible in your terminal | Claude's notes to itself from previous sessions: build commands it learned, patterns it noticed, mistakes to avoid. The first 200 lines or 25KB, whichever comes first, are loaded into the conversation context. [Learn more](./memory.md#auto-memory) |
| Environment info | Auto-loaded | 280 | Invisible in your terminal | Working directory, platform, shell, OS version, and whether this is a git repo. Git branch, status, and recent commits load as a separate block at the very end of the system prompt. |
| MCP tools (deferred) | Auto-loaded | 120 | Invisible in your terminal | MCP tool names listed so Claude knows what is available. By default, full schemas stay deferred and Claude loads specific ones on demand via tool search when a task needs them. Set `ENABLE_TOOL_SEARCH=auto` to load schemas upfront when they fit within 10% of the context window, or `ENABLE_TOOL_SEARCH=false` to load everything. [Learn more](./mcp.md#scale-with-mcp-tool-search) |
| Skill descriptions | Auto-loaded | 450 | Invisible in your terminal | One-line descriptions of available skills so Claude knows what it can invoke. Full skill content loads only when Claude actually uses one. Skills with `disable-model-invocation: true` are not in this list. They stay completely out of context until you invoke them with `/name`. Unlike the rest of the startup content, this listing is not re-injected after `/compact`. Only skills you actually invoked get preserved. [Learn more](./skills.md) |
| ~/.claude/CLAUDE.md | Auto-loaded | 320 | Invisible in your terminal | Your global preferences. Applies to every project. Loaded alongside project instructions at the start of every conversation. [Learn more](./memory.md#choose-where-to-put-claude-md-files) |
| Project CLAUDE.md | Auto-loaded | 1,800 | Invisible in your terminal | Project conventions, build commands, architecture notes. The most important file you can create. Lives in your project root, so your whole team gets the same instructions. *Keep it under 200 lines. Move reference content to skills or path-scoped rules so it only loads when needed.* [Learn more](./memory.md) |
| Your prompt | You typed this | 45 | Shown in your terminal | "Fix the auth bug where users get 401 after token refresh" |
| Read src/api/auth.ts | Claude's work | 2,400 | One-liner in your terminal | Main auth file. You see "Read auth.ts" in your terminal, but the 2,400 tokens of file content only Claude sees. *File reads dominate context usage. Be specific in prompts ("fix the bug in auth.ts") so Claude reads fewer files. For research-heavy tasks, use a subagent.* |
| Read src/lib/tokens.ts | Claude's work | 1,100 | One-liner in your terminal | Following imports to the token module. Shown as a one-liner in your terminal. |
| Rule: api-conventions.md | Auto-loaded | 380 | One-liner in your terminal | This rule in `.claude/rules/` has a `paths:` pattern matching `src/api/**`. It loaded automatically when Claude read a file in that directory. You see "Loaded .claude/rules/api-conventions.md" in your terminal, but not the rule content. [Learn more](./memory.md#path-specific-rules) |
| Read middleware.ts | Claude's work | 1,800 | One-liner in your terminal | Tracing the auth flow deeper. |
| Read auth.test.ts | Claude's work | 1,600 | One-liner in your terminal | Checking existing tests for expected behavior. |
| Rule: testing.md | Auto-loaded | 290 | One-liner in your terminal | Another path-scoped rule, this one matching `*.test.ts` files. Triggered when Claude read auth.test.ts. Shown as a one-line "Loaded" notice. [Learn more](./memory.md#path-specific-rules) |
| grep "refreshToken" | Claude's work | 600 | One-liner in your terminal | Search results across the codebase. You see the command ran, not the full output. |
| Claude's analysis | Claude's work | 800 | Shown in your terminal | Explains the bug: token invalidated too early in the rotation. This text appears in your terminal. |
| Edit auth.ts | Claude's work | 400 | Shown in your terminal | Fixes the token rotation order. The diff appears in your terminal. |
| Hook: prettier | Hook (automatic) | 120 | Invisible in your terminal | A PostToolUse hook in `settings.json` runs prettier after every file edit and reports back via `hookSpecificOutput.additionalContext`. That field enters Claude's context. Plain stdout on exit 0 does not. It is written to the debug log only. *Output JSON with `additionalContext` to send info to Claude. For PostToolUse hooks, exit code 2 surfaces stderr as an error but cannot block since the tool already ran. Output over 10,000 characters is saved to a file; Claude gets a preview and the file path instead.* [Learn more](./hooks-guide.md) |
| Edit auth.test.ts | Claude's work | 600 | Shown in your terminal | Adds a regression test for the fix. The diff appears in your terminal. |
| Hook: prettier | Hook (automatic) | 100 | Invisible in your terminal | The same hook fires again for the test file. Every matching tool event triggers it. [Learn more](./hooks-guide.md) |
| npm test output | Claude's work | 1,200 | One-liner in your terminal | Runs the test suite. You see "Running npm test..." and the pass count, not the full 1,200 tokens of output. |
| Summary | Claude's work | 400 | Shown in your terminal | "Fixed token rotation. Added regression test. All tests pass." |
| Your follow-up | You typed this | 40 | Shown in your terminal | "Use a subagent to research session timeout handling, then fix it" *Follow-ups add to the same context. Delegating research to a subagent keeps large file reads out of your main window.* |
| Spawn research subagent | Claude's work | 80 | One-liner in your terminal | Claude delegates the research to a subagent with a fresh, separate context window. It loads CLAUDE.md and the same MCP and skill setup, but starts without your conversation history or the main session's auto memory. [Learn more](./sub-agents.md) |
| System prompt | In subagent's context | 900 | Invisible in your terminal | The subagent gets its own system prompt, shorter than the main session's. For the general-purpose agent, it's a brief prompt plus environment details. The main session's auto memory is not included. If a custom agent has memory: in its frontmatter, it loads its own separate MEMORY.md here instead. [Learn more](./sub-agents.md#enable-persistent-memory) |
| Project CLAUDE.md (own copy) | In subagent's context | 1,800 | Invisible in your terminal | The subagent loads CLAUDE.md too. Same file, same content, but it counts against the subagent's context, not yours. The built-in Explore and Plan agents skip this for a smaller context. [Learn more](./sub-agents.md) |
| MCP tools + skills | In subagent's context | 970 | Invisible in your terminal | The subagent has access to the same MCP servers and skills. It gets most of the parent's tools, minus several that don't apply in a nested context, including plan-mode controls, background-task tools, and by default the Agent tool itself to prevent recursion. [Learn more](./sub-agents.md) |
| Task prompt from main | In subagent's context | 120 | Invisible in your terminal | Instead of a user prompt, the subagent receives the task Claude wrote for it: 'Research session timeout handling in this codebase.' [Learn more](./sub-agents.md) |
| Read session.ts | In subagent's context | 2,200 | Invisible in your terminal | Now the subagent does its work. This file read fills the subagent's context, not yours. [Learn more](./sub-agents.md) |
| Read timeouts.ts | In subagent's context | 800 | Invisible in your terminal | Another file read in the subagent's separate context. [Learn more](./sub-agents.md) |
| Read config/*.ts | In subagent's context | 3,100 | Invisible in your terminal | The subagent can read as many files as it needs. None of this touches your main context. [Learn more](./sub-agents.md) |
| Subagent returns summary | Claude's work | 420 | One-liner in your terminal | Only the subagent's final text response comes back to your context, plus a small metadata trailer with token counts and duration. The subagent read 6,100 tokens of files. You got a 420-token result. That's the context savings. [Learn more](./sub-agents.md) |
| Claude's response | Claude's work | 1,200 | Shown in your terminal | Analysis and fix for session timeouts. This text appears in your terminal. |
| !git status | You typed this | 180 | Shown in your terminal | You ran a shell command with the ! prefix to see which files Claude modified. The command and its output both enter context as part of your message. Useful for grounding Claude in command output without Claude running it. [Learn more](./interactive-mode.md#shell-mode-with-prefix) |
| /commit-push | You typed this | 620 | One-liner in your terminal | You invoked a skill that has `disable-model-invocation: true`. Its description was not in the skill index at startup, so it cost zero context until this moment. Now the full skill content loads and Claude follows its instructions to stage, commit, and push your changes. After `/compact`, Claude Code re-injects the body of each skill you invoked, capped at 5,000 tokens per skill. *Set `disable-model-invocation: true` on skills with side effects like committing, deploying, or sending messages. They stay out of context entirely until you need them.* [Learn more](./skills.md#control-who-invokes-a-skill) |
| /compact | Compaction |  | One-liner in your terminal | Replaces the conversation with a structured summary. You see a "Conversation compacted" message. The summarization happens without appearing in your terminal. [Learn more](./how-claude-code-works.md#the-context-window) |

```jsx
export const ContextWindow = () => {

  const STARTUP_END = 0.2;
  {}


  {}
  const GATES = [{
    at: 0.18,
    kind: 'prompt',
    text: 'Fix the auth bug where users get 401 after token refresh',
    resumeTo: 0.22
  }, {
    at: 0.705,
    kind: 'prompt',
    text: 'Use a subagent to research session timeout handling, then fix it',
    resumeTo: 0.72
  }, {
    at: 0.865,
    kind: 'bang',
    text: '!git status',
    resumeTo: 0.875
  }, {
    at: 0.88,
    kind: 'slash',
    text: '/commit-push',
    resumeTo: 0.89
  }, {
    at: 0.90,
    kind: 'compact',
    text: '/compact',
    resumeTo: 1
  }];

  const LEGEND = [{
    c: '#6B6964',
    l: 'System'
  }, {
    c: '#6A9BCC',
    l: 'CLAUDE.md'
  }, {
    c: '#E8A45C',
    l: 'Memory'
  }, {
    c: '#D4A843',
    l: 'Skills'
  }, {
    c: '#9B7BC4',
    l: 'MCP'
  }, {
    c: '#4A9B8E',
    l: 'Rules'
  }, {
    c: '#558A42',
    l: 'You'
  }, {
    c: '#8A8880',
    l: 'Files'
  }, {
    c: '#A09E96',
    l: 'Output'
  }, {
    c: '#D97757',
    l: 'Claude'
  }, {
    c: '#B8860B',
    l: 'Hooks'
  }];
  const fmt = n => n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K' : n + '';
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [hovIdx, setHovIdx] = useState(null);
  const [selIdx, setSelIdx] = useState(null);
  const [hovCat, setHovCat] = useState(null);
  const [gatesPassed, setGatesPassed] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [hasInteracted, setHasInteracted] = useState(false);
  const lastRef = useRef(null);
  const scrollRef = useRef(null);
  const detailRef = useRef(null);
  useEffect(() => setMounted(true), []);
  const activeGate = GATES.find((g, i) => i >= gatesPassed && time >= g.at && time < g.resumeTo);
  useEffect(() => {
    if (!playing) return;
    let raf;
    let stopped = false;
    const tick = ts => {
      if (stopped) return;
      if (!lastRef.current) lastRef.current = ts;
      const dt = (ts - lastRef.current) / 1000;
      lastRef.current = ts;
      setTime(prev => {
        const next = prev + dt * 0.032;
        const gate = GATES.find((g, i) => i >= gatesPassed && next >= g.at && prev < g.resumeTo);
        if (gate) {
          stopped = true;
          setPlaying(false);
          return gate.at;
        }
        if (next >= 1) {
          stopped = true;
          setPlaying(false);
          return 1;
        }
        return next;
      });
      if (!stopped) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      lastRef.current = null;
    };
  }, [playing, gatesPassed]);
  const sendPrompt = () => {
    if (!activeGate) return;
    const isCompact = activeGate.kind === 'compact';
    setGatesPassed(n => n + 1);
    setTime(activeGate.resumeTo);
    setSelIdx(null);
    setHovIdx(null);
    if (!isCompact) setPlaying(true);
  };
  const visibleCount = EVENTS.filter(e => e.t <= time).length;
  const preCompactVisible = useMemo(() => EVENTS.slice(0, visibleCount), [EVENTS, visibleCount]);
  const compactGateIdx = GATES.length - 1;
  const isCompacted = gatesPassed > compactGateIdx && preCompactVisible.some(e => e.kind === 'compact');
  const {visible, preCompactTotal} = useMemo(() => {
    const nonCompact = preCompactVisible.filter(e => e.kind !== 'compact');
    if (!isCompacted) {
      return {
        visible: preCompactVisible,
        preCompactTotal: 0
      };
    }
    {}
    const autoLoads = nonCompact.filter(e => e.kind === 'auto' && e.t < STARTUP_END && !e.noSurviveCompact);
    const restored = nonCompact.filter(e => e.restoredAfterCompact);
    const summarized = nonCompact.filter(e => e.t >= STARTUP_END && e.kind !== 'sub');
    const sumTokens = summarized.reduce((s, e) => s + e.tokens, 0);
    const summaryBlock = {
      t: STARTUP_END,
      kind: 'compact',
      label: 'Conversation summary',
      tokens: Math.round(sumTokens * 0.12),
      color: '#A09E96',
      vis: 'hidden',
      desc: `All ${summarized.length} conversation events condensed into one structured summary. The summary keeps: your requests and intent, key technical concepts, files examined or modified with important code snippets, errors and how they were fixed, pending tasks, and current work. It replaces the verbatim conversation: full tool outputs and intermediate reasoning are gone. Claude Code re-reads the files modified most recently and re-injects the skills you invoked, listed below. Claude can still reference the rest of the work but won't have the exact content.`,
      link: '/en/how-claude-code-works#the-context-window'
    };
    return {
      visible: [...autoLoads, summaryBlock, ...restored],
      preCompactTotal: nonCompact.reduce((s, e) => s + e.tokens, 0)
    };
  }, [preCompactVisible, isCompacted]);
  const {blocks, totalTokens} = useMemo(() => {
    const bl = visible.map((e, visIdx) => ({
      ...e,
      id: e.label + e.t,
      visIdx
    })).filter(e => e.tokens > 0 || e.label === 'Conversation summary');
    return {
      blocks: bl,
      totalTokens: bl.reduce((s, b) => s + b.tokens, 0)
    };
  }, [visible]);
  const subTotal = useMemo(() => visible.filter(e => e.kind === 'sub').reduce((s, e) => s + (e.subTokens || 0), 0), [visible]);
  useEffect(() => {
    if (!scrollRef.current) return;
    if (isCompacted) scrollRef.current.scrollTo({
      top: 0,
      behavior: 'smooth'
    }); else if (playing || activeGate) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [visible.length, !!activeGate, isCompacted]);
  const rootRef = useRef(null);
  const keyStateRef = useRef({});
  const [isFullscreen, setIsFullscreen] = useState(false);
  keyStateRef.current = {
    time,
    activeGate,
    sendPrompt,
    hasInteracted
  };
  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);
  const toggleFullscreen = () => {
    if (!rootRef.current) return;
    if (document.fullscreenElement) document.exitFullscreen(); else rootRef.current.requestFullscreen().catch(() => {});
  };
  useEffect(() => {
    const onKey = e => {
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'BUTTON' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) return;
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;
      if (rect.bottom < 0 || rect.top > window.innerHeight) return;
      if (e.code === 'Space') {
        const {time: t, activeGate: g, sendPrompt: send, hasInteracted: hi} = keyStateRef.current;
        if (!hi) return;
        e.preventDefault();
        if (t === 0) setPlaying(true); else if (g) send(); else if (t >= 1) {
          setTime(0);
          setGatesPassed(0);
          setSelIdx(null);
          setHovIdx(null);
          setPlaying(true);
        } else setPlaying(p => !p);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const pct = totalTokens / MAX * 100;
  const barColor = pct > 75 ? '#D97757' : pct > 50 ? '#B8860B' : '#558A42';
  const activeIdx = selIdx !== null ? selIdx : hovIdx;
  const hovEvent = activeIdx !== null ? visible[activeIdx] : null;
  useEffect(() => {
    if (detailRef.current) detailRef.current.scrollTop = 0;
  }, [hovEvent]);
  const focusT = hovEvent ? hovEvent.t : time;
  const takeaway = isCompacted ? 'Compaction replaces the conversation with a structured summary. System prompt, CLAUDE.md, memory, and MCP tools reload automatically. Claude Code also re-reads up to five of the files modified most recently, reloads the rules that match them, and re-injects the skills you invoked. The skill listing does not reload.' : focusT < STARTUP_END ? 'A lot loads before you type anything. CLAUDE.md, memory, skills, and MCP tools are all in context before your first prompt.' : focusT < 0.28 ? "Your prompt is tiny compared to what's already loaded. Most of Claude's context is project knowledge, not your words." : focusT < 0.50 ? 'Each file Claude reads grows the context. Path-scoped rules load automatically alongside matching files.' : focusT < 0.71 ? 'Hooks fire automatically on tool events. Output reaches Claude via additionalContext JSON. Exit code 2 surfaces stderr to Claude. Plain stdout on exit 0 goes to the debug log, not the transcript.' : focusT < 0.79 ? 'Follow-up questions keep building on the same context. Everything from earlier is still there.' : focusT < 0.87 ? "The subagent works in its own separate context window. None of its file reads touch yours. Only the final summary comes back." : focusT < 0.88 ? 'Bang commands run in your shell and prefix the output to your next message. Useful for grounding Claude in command results without it running them.' : focusT < 0.90 ? 'User-only skills stay out of context entirely until you invoke them. The skill index at startup only lists skills Claude can call on its own.' : '/compact summarizes the conversation to free space while keeping key information. In a real session, run it when context starts affecting performance or before a long new task.';
  const terminalView = isCompacted ? 'A "Conversation compacted" message, then a one-line "Read auth.ts" for each re-read file and "Skills restored (commit-push)". The rules show as "Loaded" lines on Claude\'s next turn. None of the content itself appears.' : focusT < STARTUP_END ? 'The input box, waiting for your first message. Everything above loads silently before you type anything.' : focusT < 0.28 ? 'Your prompt. Claude hasn\'t started working yet.' : focusT < 0.52 ? 'Your prompt and "Reading files...". Rules show as one-line "Loaded" notices, not their content.' : focusT < 0.72 ? "Claude's response and file diffs. Hooks fire silently. Tool output like npm test shows as a brief summary, not the full content." : focusT < 0.79 ? 'Your follow-up prompt.' : focusT < 0.86 ? "A brief notice that a subagent is working, then its result. You don't see the subagent's individual file reads." : focusT < 0.90 ? "Claude's response, your git status output, and the commit-push skill running." : 'Your full conversation. /compact is available to run.';
  const mono = 'var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)';
  const renderWithCode = s => s.split('`').map((part, i) => i % 2 === 1 ? <code key={i} style={{
    fontFamily: mono,
    fontSize: '0.92em',
    background: 'var(--cw-track)',
    padding: '1px 4px',
    borderRadius: 3
  }}>{part}</code> : part);
  if (!mounted) return null;
  return <>
    <div className="cw-mobile-fallback">
      This interactive timeline works best on a larger screen. See <a href="#what-the-timeline-shows" style={{
    color: '#D97757'
  }}>the written breakdown below</a> for the same concepts.
    </div>
    <div className="cw-root" ref={rootRef} onClickCapture={() => setHasInteracted(true)} style={isFullscreen ? {
    height: '100vh',
    borderRadius: 0,
    display: 'flex',
    flexDirection: 'column'
  } : {}}>
      <style>{`
        .cw-root {
          --cw-bg: #FAFAF8;
          --cw-text: #1A1918;
          --cw-text-2: #3D3C38;
          --cw-text-3: #5E5D59;
          --cw-text-dim: #6E6C64;
          --cw-text-faint: #8A8880;
          --cw-surface: rgba(0,0,0,0.025);
          --cw-surface-2: rgba(0,0,0,0.04);
          --cw-border: rgba(0,0,0,0.08);
          --cw-track: rgba(0,0,0,0.04);
          --cw-hover: rgba(0,0,0,0.04);
          --cw-rail: rgba(0,0,0,0.08);
          --cw-scrollbar: rgba(0,0,0,0.22);
          background: var(--cw-bg);
          border-radius: 12px;
          overflow: hidden;
          font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, sans-serif);
          color: var(--cw-text);
          border: 1px solid var(--cw-border);
        }
        .dark .cw-root {
          --cw-bg: #111110;
          --cw-text: #E8E6DC;
          --cw-text-2: #B8B6AE;
          --cw-text-3: #9C9A92;
          --cw-text-dim: #8A8880;
          --cw-text-faint: #6E6C64;
          --cw-surface: rgba(255,255,255,0.02);
          --cw-surface-2: rgba(255,255,255,0.015);
          --cw-border: rgba(255,255,255,0.06);
          --cw-track: rgba(255,255,255,0.03);
          --cw-hover: rgba(255,255,255,0.04);
          --cw-rail: rgba(255,255,255,0.04);
          --cw-scrollbar: rgba(255,255,255,0.18);
        }
        .cw-scroll::-webkit-scrollbar { width: 6px; }
        .cw-scroll::-webkit-scrollbar-track { background: transparent; }
        .cw-scroll::-webkit-scrollbar-thumb { background: var(--cw-scrollbar); border-radius: 3px; }
        @keyframes cw-blink { 50% { opacity: 0; } }
        @keyframes cw-fadein { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
        .cw-compacted-row { animation: cw-fadein 0.3s ease-out backwards; }
        .cw-mobile-fallback { display: none; padding: 14px 16px; border-radius: 8px; font-size: 14px; border: 1px solid rgba(0,0,0,0.1); background: rgba(0,0,0,0.03); }
        .dark .cw-mobile-fallback { border-color: rgba(255,255,255,0.15); background: rgba(255,255,255,0.04); }
        @media (max-width: 700px) {
          .cw-root { display: none !important; }
          .cw-mobile-fallback { display: block; }
        }
      `}</style>

      {}
      <div style={{
    padding: '16px 20px 12px',
    display: 'flex',
    alignItems: 'flex-end',
    gap: 24
  }}>
        <div style={{
    flex: 1,
    minWidth: 0
  }}>
          <div style={{
    fontSize: 18,
    fontWeight: 600,
    letterSpacing: -0.3,
    lineHeight: 1
  }}>
            Explore the context window
          </div>
          <div style={{
    fontSize: 14,
    color: 'var(--cw-text-dim)',
    marginTop: 4
  }}>
            A simulated session showing what enters context and what it costs
          </div>
        </div>
        <div style={{
    textAlign: 'right',
    flexShrink: 0
  }}>
          <div style={{
    fontFamily: mono,
    fontSize: 20,
    fontWeight: 600,
    color: barColor,
    letterSpacing: -0.5,
    lineHeight: 1
  }}>
            ~{fmt(totalTokens)}<span style={{
    fontSize: 15,
    fontWeight: 500,
    marginLeft: 4
  }}>tokens</span>
          </div>
          <div style={{
    fontFamily: mono,
    fontSize: 13,
    color: 'var(--cw-text-dim)',
    marginTop: 2
  }} title="Token counts are illustrative. Actual values vary with your CLAUDE.md size, MCP servers, and file lengths.">
            / {fmt(MAX)} · illustrative
          </div>
        </div>
      </div>

      {}
      <div style={{
    padding: '0 20px'
  }}>
        <div style={{
    height: 4,
    borderRadius: 2,
    background: 'var(--cw-track)',
    overflow: 'hidden',
    marginBottom: 6
  }}>
          <div style={{
    width: pct + '%',
    height: '100%',
    background: barColor,
    transition: 'width 0.6s cubic-bezier(0.4, 0, 0.2, 1), background 0.3s'
  }} />
        </div>
        <div style={{
    height: 28,
    borderRadius: 5,
    background: 'var(--cw-track)',
    border: '1px solid var(--cw-border)',
    overflow: 'hidden',
    display: 'flex'
  }}>
          {blocks.map((b, i) => {
    const w = Math.max(b.tokens / MAX * 100, 0.15);
    const isHov = b.visIdx === activeIdx;
    const catMatch = hovCat && b.color === hovCat;
    const dimmed = hovCat ? !catMatch : activeIdx !== null && !isHov;
    return <div key={b.id} onMouseEnter={() => setHovIdx(b.visIdx)} onMouseLeave={() => setHovIdx(null)} onClick={() => setSelIdx(selIdx === b.visIdx ? null : b.visIdx)} style={{
      width: w + '%',
      height: '100%',
      background: b.color,
      opacity: isHov || catMatch ? 1 : dimmed ? 0.25 : 0.65,
      borderRight: i < blocks.length - 1 ? '0.5px solid var(--cw-border)' : 'none',
      transition: 'opacity 0.15s',
      cursor: 'pointer'
    }} />;
  })}
        </div>
        <div style={{
    display: 'flex',
    gap: 12,
    marginTop: 6,
    flexWrap: 'wrap',
    justifyContent: 'space-between'
  }}>
          <div style={{
    display: 'flex',
    gap: 12,
    flexWrap: 'wrap'
  }}>
            {LEGEND.map(x => {
    const active = hovCat === x.c;
    return <div key={x.l} onMouseEnter={() => setHovCat(x.c)} onMouseLeave={() => setHovCat(null)} style={{
      display: 'flex',
      alignItems: 'center',
      gap: 4,
      padding: '2px 6px',
      borderRadius: 4,
      cursor: 'pointer',
      background: active ? 'var(--cw-hover)' : 'transparent',
      transition: 'background 0.1s'
    }}>
                  <div style={{
      width: 6,
      height: 6,
      borderRadius: 1.5,
      background: x.c,
      opacity: active ? 1 : 0.7
    }} />
                  <span style={{
      fontSize: 12,
      color: active ? 'var(--cw-text)' : 'var(--cw-text-dim)'
    }}>{x.l}</span>
                </div>;
  })}
          </div>
          <div style={{
    display: 'flex',
    gap: 6,
    alignItems: 'center',
    fontSize: 12,
    color: 'var(--cw-text-dim)'
  }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#558A42" strokeWidth="2.5">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
            </svg>
            <span>= appears in your terminal</span>
          </div>
        </div>
      </div>

      {}
      <div style={{
    display: 'flex',
    padding: '14px 20px 0',
    gap: 16,
    height: isFullscreen ? 'calc(100vh - 240px)' : 420
  }}>

        {}
        <div ref={scrollRef} className="cw-scroll" style={{
    flex: 1,
    minWidth: 0,
    overflowY: 'auto',
    paddingRight: 8,
    scrollBehavior: 'smooth'
  }}>
          {visible.length === 0 && !playing && <div style={{
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16
  }}>
              <div style={{
    fontFamily: mono,
    fontSize: 16,
    color: 'var(--cw-text-dim)',
    display: 'flex',
    alignItems: 'center',
    gap: 8
  }}>
                <span style={{
    color: 'var(--cw-text-faint)'
  }}>$</span>
                <span>claude</span>
                <span style={{
    display: 'inline-block',
    width: 8,
    height: 16,
    background: 'var(--cw-text-dim)',
    opacity: 0.5,
    animation: 'cw-blink 1s step-end infinite'
  }} />
              </div>
              <button onClick={() => setPlaying(true)} style={{
    padding: '10px 20px',
    borderRadius: 8,
    border: '1px solid rgba(217,119,87,0.3)',
    background: 'rgba(217,119,87,0.08)',
    color: '#D97757',
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 8
  }}>
                <span>▶</span>
                <span>Start session</span>
              </button>
              <div style={{
    fontSize: 13,
    color: 'var(--cw-text-faint)',
    maxWidth: 280,
    textAlign: 'center',
    lineHeight: 1.5
  }}>
                Watch what loads into context, from the moment you run <code style={{
    fontFamily: mono
  }}>claude</code> through a full conversation.
              </div>
            </div>}
          {isCompacted && <div style={{
    marginBottom: 10,
    padding: '10px 12px',
    borderRadius: 6,
    background: 'rgba(217,119,87,0.05)',
    border: '1px solid rgba(217,119,87,0.15)'
  }}>
              <div style={{
    fontSize: 13,
    fontWeight: 600,
    color: '#D97757',
    marginBottom: 3
  }}>
                After /compact
              </div>
              <div style={{
    fontSize: 13,
    color: 'var(--cw-text-3)',
    lineHeight: 1.5,
    fontFamily: mono
  }}>
                {fmt(preCompactTotal)} → {fmt(totalTokens)} tokens · freed {fmt(preCompactTotal - totalTokens)}
              </div>
              <div style={{
    fontSize: 13,
    color: 'var(--cw-text-dim)',
    lineHeight: 1.5,
    marginTop: 4
  }}>
                This is what's left in context: startup content, which lives outside the message history and reloads after compaction, a structured summary of the entire conversation, the files modified most recently, which Claude Code re-reads along with the rules that match them, and the body of each skill you invoked. Skill descriptions don't reload.
              </div>
            </div>}
          {time > 0 && visible.length > 0 && <div style={{
    fontSize: 12,
    fontWeight: 700,
    color: 'var(--cw-text-faint)',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 6,
    paddingLeft: 28
  }}>
              {isCompacted ? 'Reloaded after compact' : 'Before you type anything'}
            </div>}

          {time > 0 && visible.map((evt, i) => {
    const meta = KIND_META[evt.kind];
    const isHov = hovIdx === i;
    const prevKind = i > 0 ? visible[i - 1].kind : null;
    const isSub = evt.kind === 'sub';
    const enteringSubagent = isSub && prevKind !== 'sub';
    const leavingSubagent = prevKind === 'sub' && !isSub;
    let showPhase = null;
    if (isCompacted && evt.restoredAfterCompact) {
      if (prevKind === 'compact') showPhase = 'Restored after /compact';
    } else if (evt.kind === 'user' && prevKind !== 'user') showPhase = 'You'; else if (evt.kind === 'claude' && prevKind === 'user') showPhase = 'Claude works'; else if (evt.label === 'Conversation summary') showPhase = 'Summarized by /compact';
    const isNewRow = isCompacted && !(evt.kind === 'auto' && evt.t < STARTUP_END);
    return <div key={evt.label + evt.t} className={isNewRow ? 'cw-compacted-row' : ''} style={isNewRow ? {
      animationDelay: `${i * 60}ms`
    } : {}}>
                {showPhase && <div style={{
      fontSize: 12,
      fontWeight: 700,
      color: 'var(--cw-text-faint)',
      textTransform: 'uppercase',
      letterSpacing: 0.6,
      marginTop: 14,
      marginBottom: 6,
      paddingLeft: 28
    }}>
                    {showPhase}
                  </div>}
                {enteringSubagent && <div style={{
      marginLeft: 28,
      marginTop: 6,
      marginBottom: 2,
      paddingLeft: 10,
      borderLeft: '2px solid rgba(155,123,196,0.4)',
      fontSize: 12,
      fontWeight: 600,
      color: '#9B7BC4',
      textTransform: 'uppercase',
      letterSpacing: 0.5
    }}>
                    Subagent's separate context window
                  </div>}
                {leavingSubagent && <div style={{
      marginLeft: 28,
      marginBottom: 6,
      paddingLeft: 10,
      paddingBottom: 6,
      borderLeft: '2px solid rgba(155,123,196,0.4)',
      fontSize: 12,
      color: 'var(--cw-text-dim)',
      fontFamily: mono
    }}>
                    ↓ {fmt(subTotal)} tokens stayed in subagent's context · only the summary returns
                  </div>}
                <div onMouseEnter={() => setHovIdx(i)} onMouseLeave={() => setHovIdx(null)} onClick={() => setSelIdx(selIdx === i ? null : i)} style={{
      display: 'flex',
      alignItems: 'flex-start',
      borderRadius: 6,
      cursor: 'pointer',
      background: selIdx === i || isHov ? 'var(--cw-hover)' : 'transparent',
      outline: selIdx === i ? '1px solid rgba(217,119,87,0.4)' : 'none',
      opacity: hovCat && evt.color !== hovCat ? 0.35 : 1,
      transition: 'background 0.1s, opacity 0.15s',
      marginLeft: isSub ? 28 : 0,
      paddingLeft: isSub ? 10 : 0,
      borderLeft: isSub ? '2px solid rgba(155,123,196,0.4)' : 'none'
    }}>
                  <div style={{
      width: 28,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      paddingTop: 8,
      flexShrink: 0
    }}>
                    <div style={{
      width: evt.kind === 'user' || evt.kind === 'compact' ? 10 : 7,
      height: evt.kind === 'user' || evt.kind === 'compact' ? 10 : 7,
      borderRadius: '50%',
      background: evt.color,
      opacity: isHov ? 1 : 0.6,
      transition: 'opacity 0.15s',
      boxShadow: isHov ? `0 0 8px ${evt.color}40` : 'none'
    }} />
                    {i < visible.length - 1 && <div style={{
      width: 1.5,
      flex: 1,
      background: 'var(--cw-rail)',
      marginTop: 2,
      minHeight: 6
    }} />}
                  </div>
                  <div style={{
      flex: 1,
      minWidth: 0,
      padding: '5px 10px 5px 4px',
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }}>
                    <span style={{
      fontSize: 12,
      fontWeight: 600,
      padding: '1px 5px',
      borderRadius: 3,
      background: meta.badgeBg,
      color: meta.badgeColor,
      flexShrink: 0,
      fontFamily: mono
    }}>
                      {meta.badge}
                    </span>
                    <span style={{
      fontSize: 15,
      fontFamily: mono,
      color: isHov ? 'var(--cw-text)' : evt.kind === 'user' ? '#558A42' : evt.kind === 'auto' ? 'var(--cw-text-dim)' : 'var(--cw-text-2)',
      flex: 1,
      minWidth: 0,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
      fontWeight: evt.kind === 'user' ? 550 : 400
    }}>
                      {evt.label}
                    </span>
                    {evt.tokens > 0 && <span style={{
      fontSize: 12,
      fontFamily: mono,
      color: 'var(--cw-text-faint)',
      flexShrink: 0
    }}>
                        +{fmt(evt.tokens)}
                      </span>}
                    {evt.subTokens > 0 && <span style={{
      fontSize: 12,
      fontFamily: mono,
      color: '#9B7BC4',
      flexShrink: 0,
      opacity: 0.6
    }}>
                        +{fmt(evt.subTokens)}
                      </span>}
                    {evt.tokens > 0 && <div style={{
      width: 50,
      height: 5,
      borderRadius: 2,
      background: 'var(--cw-track)',
      flexShrink: 0,
      overflow: 'hidden'
    }}>
                        <div style={{
      width: Math.min(evt.tokens / 5000 * 100, 100) + '%',
      height: '100%',
      background: evt.color,
      opacity: isHov ? 0.8 : 0.4,
      transition: 'opacity 0.15s'
    }} />
                      </div>}
                    <span style={{
      width: 14,
      flexShrink: 0,
      display: 'flex',
      justifyContent: 'center'
    }} title={VIS_META[evt.vis].label}>
                      {evt.vis !== 'hidden' && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={evt.vis === 'full' ? '#558A42' : 'currentColor'} style={{
      color: 'var(--cw-text-faint)',
      opacity: evt.vis === 'full' ? 1 : 0.5
    }} strokeWidth="2">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                        </svg>}
                    </span>
                  </div>
                </div>
              </div>;
  })}

          {activeGate && (activeGate.kind === 'prompt' || activeGate.kind === 'bang' || activeGate.kind === 'slash') && <div style={{
    paddingLeft: 28,
    marginTop: 12,
    paddingRight: 8
  }}>
              <div style={{
    fontSize: 11,
    fontWeight: 600,
    color: '#6BA656',
    fontFamily: mono,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 4,
    paddingLeft: 2
  }}>
                You type in your terminal
              </div>
              <div style={{
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    padding: '10px 12px',
    borderRadius: 6,
    background: 'rgba(85,138,66,0.06)',
    border: '1px solid rgba(85,138,66,0.2)'
  }}>
                <span style={{
    color: '#558A42',
    fontSize: 15,
    fontFamily: mono,
    flexShrink: 0
  }}>❯</span>
                <span style={{
    fontSize: 15,
    fontFamily: mono,
    color: 'var(--cw-text-2)',
    flex: 1,
    lineHeight: 1.5
  }}>
                  {activeGate.text}
                  <span style={{
    display: 'inline-block',
    width: 7,
    height: 13,
    marginLeft: 2,
    background: '#558A42',
    opacity: 0.5,
    verticalAlign: 'middle',
    animation: 'cw-blink 1s step-end infinite'
  }} />
                </span>
                <button onClick={sendPrompt} style={{
    padding: '5px 12px',
    borderRadius: 5,
    border: 'none',
    background: '#558A42',
    color: '#fff',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    flexShrink: 0
  }}>
                  {activeGate.kind === 'prompt' ? 'Send ↵' : 'Run ↵'}
                </button>
              </div>
            </div>}
          {activeGate && activeGate.kind === 'compact' && <div style={{
    paddingLeft: 28,
    marginTop: 12,
    paddingRight: 8
  }}>
              <div style={{
    padding: '12px 14px',
    borderRadius: 6,
    background: 'rgba(217,119,87,0.06)',
    border: '1px solid rgba(217,119,87,0.25)'
  }}>
                <div style={{
    fontSize: 13,
    color: 'var(--cw-text-3)',
    marginBottom: 8,
    lineHeight: 1.5
  }}>
                  Context is at <span style={{
    fontFamily: mono,
    fontWeight: 600,
    color: barColor
  }}>{fmt(totalTokens)} tokens</span>.
                  Run <code style={{
    fontFamily: mono,
    background: 'var(--cw-track)',
    padding: '1px 4px',
    borderRadius: 3
  }}>/compact</code> to
                  summarize older exchanges and free space for more work.
                </div>
                <div style={{
    display: 'flex',
    alignItems: 'center',
    gap: 8
  }}>
                  <span style={{
    color: '#D97757',
    fontSize: 15,
    fontFamily: mono
  }}>❯</span>
                  <span style={{
    fontSize: 15,
    fontFamily: mono,
    color: 'var(--cw-text-2)',
    flex: 1
  }}>
                    {activeGate.text}
                  </span>
                  <button onClick={sendPrompt} style={{
    padding: '5px 12px',
    borderRadius: 5,
    border: 'none',
    background: '#D97757',
    color: '#fff',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    flexShrink: 0
  }}>
                    Run ↵
                  </button>
                </div>
              </div>
            </div>}
        </div>

        {}
        <div style={{
    width: 300,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column'
  }}>
          <div ref={detailRef} className="cw-scroll" style={{
    padding: '14px 16px',
    borderRadius: 10,
    background: 'var(--cw-surface)',
    border: '1px solid var(--cw-border)',
    flex: 1,
    minHeight: 0,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 10
  }}>
            {hovEvent ? <div>
                <div style={{
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8
  }}>
                  <div style={{
    width: 10,
    height: 10,
    borderRadius: 3,
    background: hovEvent.color,
    opacity: 0.8
  }} />
                  <span style={{
    fontSize: 16,
    fontWeight: 600
  }}>{hovEvent.label}</span>
                </div>
                <div style={{
    display: 'flex',
    width: 'fit-content',
    padding: '3px 8px',
    borderRadius: 4,
    marginBottom: 8,
    background: KIND_META[hovEvent.kind].badgeBg
  }}>
                  <span style={{
    fontSize: 12,
    fontWeight: 600,
    color: KIND_META[hovEvent.kind].badgeColor
  }}>
                    {KIND_META[hovEvent.kind].detail}
                  </span>
                </div>
                {hovEvent.tokens > 0 && <div style={{
    fontSize: 14,
    fontFamily: mono,
    color: 'var(--cw-text-dim)',
    marginBottom: 6
  }}>
                    {fmt(hovEvent.tokens)} tokens
                  </div>}
                {hovEvent.subTokens > 0 && <div style={{
    fontSize: 14,
    fontFamily: mono,
    color: '#9B7BC4',
    marginBottom: 6
  }}>
                    {fmt(hovEvent.subTokens)} tokens in the subagent's context
                  </div>}
                <p style={{
    fontSize: 15,
    color: 'var(--cw-text-3)',
    lineHeight: 1.55,
    margin: 0
  }}>
                  {renderWithCode(hovEvent.desc)}
                </p>
                <div style={{
    marginTop: 10,
    padding: '8px 10px',
    borderRadius: 6,
    background: hovEvent.vis === 'full' ? 'rgba(85,138,66,0.08)' : 'var(--cw-surface-2)',
    border: '1px solid ' + (hovEvent.vis === 'full' ? 'rgba(85,138,66,0.2)' : 'var(--cw-border)')
  }}>
                  <div style={{
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    marginBottom: 3
  }}>
                    <span style={{
    fontSize: 13,
    color: hovEvent.vis === 'full' ? '#558A42' : 'var(--cw-text-dim)'
  }}>
                      {hovEvent.vis === 'full' ? '●' : hovEvent.vis === 'brief' ? '◐' : '○'}
                    </span>
                    <span style={{
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--cw-text-2)'
  }}>
                      {VIS_META[hovEvent.vis].label}
                    </span>
                  </div>
                  <div style={{
    fontSize: 13,
    color: 'var(--cw-text-dim)',
    lineHeight: 1.4
  }}>
                    {VIS_META[hovEvent.vis].sub}
                  </div>
                </div>
                {hovEvent.tip && <div style={{
    marginTop: 10,
    padding: '8px 10px',
    borderRadius: 6,
    background: 'rgba(85,138,66,0.06)',
    border: '1px solid rgba(85,138,66,0.15)'
  }}>
                    <div style={{
    fontSize: 12,
    fontWeight: 600,
    color: '#558A42',
    marginBottom: 3,
    display: 'flex',
    alignItems: 'center',
    gap: 4
  }}>
                      <span>💡</span> Save context
                    </div>
                    <div style={{
    fontSize: 13,
    color: 'var(--cw-text-3)',
    lineHeight: 1.5
  }}>
                      {renderWithCode(hovEvent.tip)}
                    </div>
                  </div>}
                {hovEvent.link && <a href={hovEvent.link} style={{
    display: 'inline-block',
    marginTop: 10,
    fontSize: 13,
    color: '#D97757',
    textDecoration: 'none',
    borderBottom: '1px solid rgba(217,119,87,0.3)'
  }}>
                    Learn more →
                  </a>}
              </div> : <div style={{
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    textAlign: 'center',
    gap: 4,
    padding: '12px 0 4px'
  }}>
                <div style={{
    fontSize: 22,
    opacity: 0.2
  }}>👁</div>
                <div style={{
    fontSize: 14,
    fontWeight: 500,
    color: 'var(--cw-text-dim)'
  }}>Hover or click any event</div>
                <div style={{
    fontSize: 12,
    color: 'var(--cw-text-faint)',
    lineHeight: 1.4,
    maxWidth: 200
  }}>
                  Hover to preview. Click to pin so you can scroll.
                </div>
              </div>}

            <div style={{
    padding: '10px 12px',
    borderRadius: 8,
    background: 'rgba(217,119,87,0.05)',
    border: '1px solid rgba(217,119,87,0.12)'
  }}>
              <div style={{
    fontSize: 11,
    fontWeight: 700,
    color: '#D97757',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 3
  }}>
                Key takeaway
              </div>
              <div style={{
    fontSize: 13,
    color: 'var(--cw-text-3)',
    lineHeight: 1.5
  }}>
                {takeaway}
              </div>
            </div>

            <div style={{
    padding: '10px 12px',
    borderRadius: 8,
    background: 'var(--cw-surface-2)',
    border: '1px solid var(--cw-border)'
  }}>
              <div style={{
    fontSize: 11,
    fontWeight: 700,
    color: 'var(--cw-text-dim)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 3
  }}>
                In your terminal you see
              </div>
              <div style={{
    fontSize: 13,
    color: 'var(--cw-text-3)',
    lineHeight: 1.5
  }}>
                {terminalView}
              </div>
            </div>
          </div>
        </div>
      </div>

      {}
      <div style={{
    padding: '10px 20px 14px',
    display: 'flex',
    alignItems: 'center',
    gap: 10
  }}>
        <button aria-label={time >= 1 ? 'Restart' : activeGate ? 'Continue' : playing ? 'Pause' : 'Play'} onClick={() => {
    if (time >= 1) {
      setTime(0);
      setGatesPassed(0);
      setSelIdx(null);
      setHovIdx(null);
      setPlaying(true);
    } else if (activeGate) sendPrompt(); else setPlaying(!playing);
  }} style={{
    width: 30,
    height: 30,
    borderRadius: 6,
    border: 'none',
    background: 'rgba(217,119,87,0.1)',
    color: '#D97757',
    cursor: 'pointer',
    fontSize: 15,
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  }}>
          {time >= 1 ? '↺' : playing ? '⏸' : '▶'}
        </button>
        <div style={{
    flex: 1,
    height: 3,
    borderRadius: 2,
    background: 'var(--cw-track)',
    overflow: 'hidden'
  }}>
          <div style={{
    width: time * 100 + '%',
    height: '100%',
    background: '#D97757',
    transition: 'width 0.1s linear'
  }} />
        </div>
        <span style={{
    fontSize: 12,
    fontFamily: mono,
    color: 'var(--cw-text-faint)',
    minWidth: 30
  }}>
          {Math.round(time * 100)}%
        </span>
        <button onClick={toggleFullscreen} aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'} style={{
    width: 28,
    height: 28,
    borderRadius: 6,
    border: '1px solid var(--cw-border)',
    background: 'var(--cw-surface)',
    color: 'var(--cw-text-dim)',
    cursor: 'pointer',
    fontSize: 15,
    flexShrink: 0,
    marginLeft: 4,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center'
  }}>
          {isFullscreen ? '⤡' : '⛶'}
        </button>
      </div>
    </div>
    </>;
};
```

Claude Code's context window holds everything Claude knows about your session: your instructions, the files it reads, its own responses, and content that never appears in your terminal. The timeline below plays a full session from startup to compaction: what loads before you type, what each file read, rule, and hook adds as Claude works, and how a subagent keeps large reads out of your context. See [the written breakdown](#what-the-timeline-shows) for the same content as a list.

## What the timeline shows

The session walks through a realistic flow with representative token counts:

* **Before you type anything**: CLAUDE.md, auto memory, MCP tool names, and skill descriptions all load into context. Your own setup may add more here, like an [output style](./output-styles.md) or text from [`--append-system-prompt`](./cli-reference.md).
* **As Claude works**: each file read adds to context, [path-scoped rules](./memory.md#path-specific-rules) load automatically alongside matching files, and a [PostToolUse hook](./hooks-guide.md) fires after each edit.
* **The follow-up prompt**: a [subagent](./sub-agents.md) handles the research in its own separate context window, so the large file reads stay out of yours. Only the summary and a small metadata trailer come back.
* **At the end**: `/compact` replaces the conversation with a structured summary. Most startup content reloads automatically; the table below shows what happens to each mechanism.

## What survives compaction

When a long session compacts, Claude Code summarizes the conversation history to fit the context window. As of v2.1.198, the summarization request inherits your session's [extended thinking](./model-config.md#extended-thinking) configuration, so it reasons with thinking enabled when your session has it enabled and stays off otherwise. Thinking affects only how the summary is produced; your session settings are unchanged afterward. What happens to each kind of content depends on how it was loaded:

| Mechanism                                                                                                | After compaction                                                                            |
| :------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------ |
| System prompt and output style                                                                           | Both still apply                                                                            |
| Project-root CLAUDE.md and unscoped rules                                                                | Re-injected from disk                                                                       |
| Auto memory                                                                                              | Re-injected from disk                                                                       |
| The plan Claude wrote in [plan mode](./permission-modes.md#analyze-before-you-edit-with-plan-mode)        | Re-injected from disk                                                                       |
| Rules with `paths:` frontmatter                                                                          | Claude Code reloads them as Claude reads files they match                                   |
| Nested CLAUDE.md in subdirectories                                                                       | Claude Code reloads them as Claude reads files in that subdirectory                         |
| Files Claude read or edited                                                                              | Claude Code re-reads up to five, most recently modified first                               |
| Invoked skill bodies                                                                                     | Re-injected, capped at 5,000 tokens per skill and 25,000 tokens total; oldest dropped first |
| Context that hooks added earlier                                                                         | Summarized with the rest of the conversation                                                |
| [SessionStart hooks](./hooks-guide.md#re-inject-context-after-compaction) that match the `compact` source | Claude Code runs them and adds their output to the compacted context                        |

Path-scoped rules and nested CLAUDE.md files load into message history when their trigger file is read, so compaction summarizes them away with everything else. Right after compaction, Claude Code re-reads up to five of the files Claude has read or edited in the session, choosing the ones modified most recently, and reloads the rules and nested CLAUDE.md files that apply to those files. A file over 5,000 tokens comes back as a path reference without its content, shown as `Referenced file` instead of `Read`. Its rules still reload. If a rule must persist across compaction, drop the `paths:` frontmatter or move it to the project-root CLAUDE.md.

Skill bodies are re-injected after compaction, but large skills are truncated to fit the per-skill cap, and the oldest invoked skills are dropped once the total budget is exceeded. Truncation keeps the start of the file, so put the most important instructions near the top of `SKILL.md`.

## When your context fills up

Claude Code compacts automatically as you approach the limit, so a full context window doesn't end your session. The automatic pass works the same way as the `/compact` step in the timeline. See [When context fills up](./how-claude-code-works.md#when-context-fills-up) for what it preserves.

You can also act before the automatic pass runs:

* **Compact with a focus**: run `/compact` with instructions, like `/compact focus on the auth bug fix`, before starting a long new task. The summary keeps what you choose instead of what the automatic pass guesses is important.
* **Compact part of the conversation**: run `/rewind`, select a message, and choose **Summarize from here** or **Summarize up to here**. See [Rewind and summarize](./checkpointing.md#rewind-and-summarize) for what each option keeps and how to guide the summary.
* **Compact earlier**: run [`/autocompact`](./commands.md#all-commands) with a token count, like `/autocompact 500k`, to set how full the context window gets before the automatic pass runs. See [Set the auto-compact window](./model-config.md#set-the-auto-compact-window) for accepted values and overrides.
* **Clear between tasks**: run `/clear` when switching to unrelated work. Old conversation crowds out the files you need next and costs tokens on every message.
* **Delegate large reads**: send research to a [subagent](./sub-agents.md) so the file contents stay in its context window, not yours.

If you need a larger window rather than a smaller conversation, Fable models, Sonnet 5, Opus 4.6 and later, and Sonnet 4.6 support a 1 million token context window. See [Extended context](./model-config.md#extended-context) for availability by plan and how to select a `[1m]` model variant. Compaction works the same way at the larger limit.

Sonnet 5 runs with the 1M context window and has no `[1m]` variant to select. See [Sonnet 5 context window](./model-config.md#sonnet-5-context-window) for its auto-compaction thresholds and the LLM gateway exception.

The point where automatic compaction runs depends on your model and configuration. See [Default auto-compact thresholds](./model-config.md#default-auto-compact-thresholds) for the boundaries per model, and [Correct the window for a gateway or custom model ID](./model-config.md#correct-the-window-for-a-gateway-or-custom-model-id) if Claude Code assumes the wrong window for your model ID, such as an [LLM gateway](./llm-gateway.md) alias.

## Check your own session

The visualization uses representative numbers. To see your actual context usage at any point, run `/context` for a live breakdown by category with optimization suggestions, including which CLAUDE.md and auto memory files loaded. Run `/memory` to open and edit those files.

## Related resources

For deeper coverage of the features shown in the timeline, see these pages:

* [Extend Claude Code](./features-overview.md): when to use CLAUDE.md vs skills vs rules vs hooks vs MCP
* [Store instructions and memories](./memory.md): CLAUDE.md hierarchy and auto memory
* [Subagents](./sub-agents.md): delegate research to a separate context window
* [Best practices](./best-practices.md): managing context as your primary constraint
* [Prompt caching](./prompt-caching.md): which actions invalidate the cached prefix
* [Reduce token usage](./costs.md#reduce-token-usage): strategies for keeping context usage low
