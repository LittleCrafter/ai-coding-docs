> ## Documentation Index
> Fetch the complete documentation index at: https://code.claude.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Add components to a plugin

> Add skills, hooks, MCP servers, and every other component type to a Claude Code plugin, with an example that validates for each.

<!--__MDX_SOURCE_BLOCK_0__-->export const PluginExplorer = ({children}) => {
<!--__MDX_SOURCE_BLOCK_0__-->  const PIECES = [{
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'manifest',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Manifest',
<!--__MDX_SOURCE_BLOCK_0__-->    path: '.claude-plugin/plugin.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: '.claude-plugin/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'plugin.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/manifest-reference#manifest-file',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the manifest reference'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'skills',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Skills',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'skills/review/SKILL.md',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'skills/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'review/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 2,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'SKILL.md'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#skills',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Skills section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'commands',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Commands',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'commands/about.md',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'commands/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'about.md'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#commands',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Commands section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'agents',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Agents',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'agents/security-reviewer.md',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'agents/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'security-reviewer.md'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#agents',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Agents section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'hooks',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Hooks',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'hooks/hooks.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'hooks/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'hooks.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#hooks',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Hooks section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'monitors',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Monitors',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'monitors/monitors.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'monitors/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'monitors.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#monitors',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Monitors section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'output-styles',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Output styles',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'output-styles/terse.md',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'output-styles/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'terse.md'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#themes-and-output-styles',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Themes and output styles section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'themes',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Themes',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'themes/dracula.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'themes/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'dracula.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#themes-and-output-styles',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Themes and output styles section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'workflows',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Workflows',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'workflows/audit-routes.js',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'workflows/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'audit-routes.js'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/workflows#distribute-a-workflow-in-a-plugin',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to Distribute a workflow in a plugin'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'bin',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Executables',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'bin/hello-plugin',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'bin/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'hello-plugin'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#executables',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Executables section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'scripts',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Scripts',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'scripts/format.sh',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'folder',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'scripts/'
<!--__MDX_SOURCE_BLOCK_0__-->    }, {
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 1,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'format.sh'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#hooks',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Hooks section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'settings',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'Default settings',
<!--__MDX_SOURCE_BLOCK_0__-->    path: 'settings.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: 'settings.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#default-settings',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the Default settings section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'mcp',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'MCP servers',
<!--__MDX_SOURCE_BLOCK_0__-->    path: '.mcp.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: '.mcp.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#mcp-servers',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the MCP servers section'
<!--__MDX_SOURCE_BLOCK_0__-->  }, {
<!--__MDX_SOURCE_BLOCK_0__-->    id: 'lsp',
<!--__MDX_SOURCE_BLOCK_0__-->    name: 'LSP servers',
<!--__MDX_SOURCE_BLOCK_0__-->    path: '.lsp.json',
<!--__MDX_SOURCE_BLOCK_0__-->    lines: [{
<!--__MDX_SOURCE_BLOCK_0__-->      depth: 0,
<!--__MDX_SOURCE_BLOCK_0__-->      kind: 'file',
<!--__MDX_SOURCE_BLOCK_0__-->      text: '.lsp.json'
<!--__MDX_SOURCE_BLOCK_0__-->    }],
<!--__MDX_SOURCE_BLOCK_0__-->    href: '/en/plugins/components#lsp-servers',
<!--__MDX_SOURCE_BLOCK_0__-->    linkText: 'Go to the LSP servers section'
<!--__MDX_SOURCE_BLOCK_0__-->  }];
<!--__MDX_SOURCE_BLOCK_0__-->  const [selectedId, setSelectedId] = useState('manifest');
<!--__MDX_SOURCE_BLOCK_0__-->  const [isFullscreen, setIsFullscreen] = useState(false);
<!--__MDX_SOURCE_BLOCK_0__-->  const rootRef = useRef(null);
<!--__MDX_SOURCE_BLOCK_0__-->  useEffect(() => {
<!--__MDX_SOURCE_BLOCK_0__-->    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
<!--__MDX_SOURCE_BLOCK_0__-->    document.addEventListener('fullscreenchange', onFsChange);
<!--__MDX_SOURCE_BLOCK_0__-->    return () => document.removeEventListener('fullscreenchange', onFsChange);
<!--__MDX_SOURCE_BLOCK_0__-->  }, []);
<!--__MDX_SOURCE_BLOCK_0__-->  const toggleFullscreen = () => {
<!--__MDX_SOURCE_BLOCK_0__-->    if (!rootRef.current) return;
<!--__MDX_SOURCE_BLOCK_0__-->    if (document.fullscreenElement) document.exitFullscreen(); else rootRef.current.requestFullscreen().catch(() => {});
<!--__MDX_SOURCE_BLOCK_0__-->  };
<!--__MDX_SOURCE_BLOCK_0__-->  const selected = PIECES.find(p => p.id === selectedId) || PIECES[0];
<!--__MDX_SOURCE_BLOCK_0__-->  const onTreeKeyDown = e => {
<!--__MDX_SOURCE_BLOCK_0__-->    const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
<!--__MDX_SOURCE_BLOCK_0__-->    if (keys.indexOf(e.key) === -1) return;
<!--__MDX_SOURCE_BLOCK_0__-->    const i = PIECES.findIndex(p => p.id === selectedId);
<!--__MDX_SOURCE_BLOCK_0__-->    let next = i;
<!--__MDX_SOURCE_BLOCK_0__-->    if (e.key === 'ArrowDown') next = Math.min(PIECES.length - 1, i + 1);
<!--__MDX_SOURCE_BLOCK_0__-->    if (e.key === 'ArrowUp') next = Math.max(0, i - 1);
<!--__MDX_SOURCE_BLOCK_0__-->    if (e.key === 'Home') next = 0;
<!--__MDX_SOURCE_BLOCK_0__-->    if (e.key === 'End') next = PIECES.length - 1;
<!--__MDX_SOURCE_BLOCK_0__-->    e.preventDefault();
<!--__MDX_SOURCE_BLOCK_0__-->    if (next === i) return;
<!--__MDX_SOURCE_BLOCK_0__-->    const id = PIECES[next].id;
<!--__MDX_SOURCE_BLOCK_0__-->    setSelectedId(id);
<!--__MDX_SOURCE_BLOCK_0__-->    const el = document.getElementById('pe-node-' + id);
<!--__MDX_SOURCE_BLOCK_0__-->    if (el) el.focus();
<!--__MDX_SOURCE_BLOCK_0__-->  };
<!--__MDX_SOURCE_BLOCK_0__-->  const FolderIcon = () => <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" aria-hidden="true">
<!--__MDX_SOURCE_BLOCK_0__-->      <path d="M1.5 4.5a1 1 0 0 1 1-1h3.2l1.3 1.5h6a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1h-10.5a1 1 0 0 1-1-1z" />
<!--__MDX_SOURCE_BLOCK_0__-->    </svg>;
<!--__MDX_SOURCE_BLOCK_0__-->  const FileIcon = () => <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" aria-hidden="true">
<!--__MDX_SOURCE_BLOCK_0__-->      <path d="M4 1.5h5.5L13 5v9.5H4z" />
<!--__MDX_SOURCE_BLOCK_0__-->      <path d="M9.5 1.5V5H13" />
<!--__MDX_SOURCE_BLOCK_0__-->    </svg>;
<!--__MDX_SOURCE_BLOCK_0__-->  return <div ref={rootRef} data-selected={selected.id}>
<!--__MDX_SOURCE_BLOCK_0__-->      <style>{`
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root {
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-mono: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-accent: #D97757;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-accent-text: #A8502F;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-accent-bg: rgba(217,119,87,0.10);
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-bg: #FFFFFF;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-surface: #FAFAF7;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-hover: #F0EEE6;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-border: #E8E6DC;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-text: #141413;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-text-2: #3D3D3A;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-text-3: #5E5D59;
<!--__MDX_SOURCE_BLOCK_0__-->          font-family: inherit;
<!--__MDX_SOURCE_BLOCK_0__-->          background: var(--pe-bg);
<!--__MDX_SOURCE_BLOCK_0__-->          color: var(--pe-text);
<!--__MDX_SOURCE_BLOCK_0__-->          border: 1px solid var(--pe-border);
<!--__MDX_SOURCE_BLOCK_0__-->          border-radius: 12px;
<!--__MDX_SOURCE_BLOCK_0__-->          margin: 1.5rem 0;
<!--__MDX_SOURCE_BLOCK_0__-->          overflow: hidden;
<!--__MDX_SOURCE_BLOCK_0__-->          box-sizing: border-box;
<!--__MDX_SOURCE_BLOCK_0__-->        }
<!--__MDX_SOURCE_BLOCK_0__-->        .dark .pe-root {
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-accent-text: #EBA98F;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-accent-bg: rgba(217,119,87,0.18);
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-bg: #1A1918;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-surface: #232221;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-hover: #2E2D2B;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-border: #3A3936;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-text: #F1EFE9;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-text-2: #D6D4CA;
<!--__MDX_SOURCE_BLOCK_0__-->          --pe-text-3: #B8B5AD;
<!--__MDX_SOURCE_BLOCK_0__-->        }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root *, .pe-root *::before, .pe-root *::after { box-sizing: border-box; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-head { display: flex; align-items: flex-start; gap: 12px; padding: 18px 24px 16px; border-bottom: 1px solid var(--pe-border); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-head-text { flex: 1; min-width: 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-fs-btn { flex-shrink: 0; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--pe-border); border-radius: 6px; background: var(--pe-surface); color: var(--pe-text-2); font-size: 15px; line-height: 1; cursor: pointer; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-fs-btn:hover { background: var(--pe-hover); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-fs-btn:focus-visible { outline: 2px solid var(--pe-accent); outline-offset: 2px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-fullscreen { border-radius: 0; height: 100vh; display: flex; flex-direction: column; overflow: auto; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-fullscreen .pe-body { flex: 1; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-title { font-size: 19px; font-weight: 600; line-height: 1.3; color: var(--pe-text); margin: 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-sub { font-size: 15px; line-height: 1.5; color: var(--pe-text-3); margin: 4px 0 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-sub code { font-family: var(--pe-mono); font-size: 0.88em; padding: 1px 5px; border-radius: 4px; background: var(--pe-surface); border: 1px solid var(--pe-border); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-body { display: flex; align-items: stretch; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-tree-pane { width: 270px; flex-shrink: 0; background: var(--pe-surface); border-right: 1px solid var(--pe-border); padding: 16px 0 12px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-panel { flex: 1; min-width: 0; padding: 16px 24px 24px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-caption { font-size: 13px; font-weight: 600; color: var(--pe-text-3); margin: 0 0 10px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-tree-pane .pe-caption { padding: 0 16px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-rootline { display: flex; align-items: center; gap: 7px; padding: 3px 16px; font-family: var(--pe-mono); font-size: 13.5px; color: var(--pe-text-3); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-node {
<!--__MDX_SOURCE_BLOCK_0__-->          display: block; width: 100%; margin: 0; padding: 3px 16px 3px 30px; text-align: left; cursor: pointer;
<!--__MDX_SOURCE_BLOCK_0__-->          background: transparent; color: var(--pe-text-2);
<!--__MDX_SOURCE_BLOCK_0__-->          border: none; border-left: 3px solid transparent;
<!--__MDX_SOURCE_BLOCK_0__-->          font-family: var(--pe-mono); font-size: 13.5px; line-height: 1.4;
<!--__MDX_SOURCE_BLOCK_0__-->        }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-node:hover { background: var(--pe-hover); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-node:focus-visible { outline: 2px solid var(--pe-accent); outline-offset: -2px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-node[aria-pressed="true"] { background: var(--pe-accent-bg); border-left-color: var(--pe-accent); color: var(--pe-accent-text); font-weight: 600; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-line { display: flex; align-items: center; gap: 7px; padding: 2px 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-line-tree { flex-wrap: wrap; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-line-tree .pe-req { flex-basis: 100%; margin: 2px 0 0 22px; white-space: normal; width: fit-content; max-width: calc(100% - 22px); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-line span { overflow-wrap: anywhere; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece { display: none; font-size: 16px; line-height: 1.6; color: var(--pe-text-2); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="manifest"] .pe-piece[data-piece="manifest"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="skills"] .pe-piece[data-piece="skills"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="commands"] .pe-piece[data-piece="commands"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="agents"] .pe-piece[data-piece="agents"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="hooks"] .pe-piece[data-piece="hooks"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="monitors"] .pe-piece[data-piece="monitors"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="output-styles"] .pe-piece[data-piece="output-styles"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="themes"] .pe-piece[data-piece="themes"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="workflows"] .pe-piece[data-piece="workflows"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="bin"] .pe-piece[data-piece="bin"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="scripts"] .pe-piece[data-piece="scripts"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="settings"] .pe-piece[data-piece="settings"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="mcp"] .pe-piece[data-piece="mcp"],
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-root[data-selected="lsp"] .pe-piece[data-piece="lsp"] { display: block; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece p { margin: 0 0 10px; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece p:last-child { margin-bottom: 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece code { font-family: var(--pe-mono); font-size: 0.88em; padding: 1px 5px; border-radius: 4px; background: var(--pe-surface); border: 1px solid var(--pe-border); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece .code-block { margin: 12px 0 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece pre code { padding: 0; border: none; background: none; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-piece a { color: var(--pe-accent-text); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-line-compact { display: none; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-icon { flex-shrink: 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-req { margin-left: 8px; padding: 0 6px; border-radius: 999px; font-size: 11px; line-height: 18px; letter-spacing: .02em; color: var(--pe-accent-text); border: 1px solid var(--pe-border); background: var(--pe-surface); white-space: nowrap; font-weight: 500; vertical-align: middle; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-name { font-size: 22px; font-weight: 600; line-height: 1.25; letter-spacing: -0.2px; color: var(--pe-text); margin: 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-path { font-family: var(--pe-mono); font-size: 13.5px; color: var(--pe-accent-text); margin: 4px 0 0; overflow-wrap: anywhere; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-block { margin: 20px 0 0; }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-link {
<!--__MDX_SOURCE_BLOCK_0__-->          display: inline-block; margin: 24px 0 0; padding: 8px 14px; border-radius: 8px;
<!--__MDX_SOURCE_BLOCK_0__-->          font-size: 14.5px; font-weight: 600; text-decoration: none;
<!--__MDX_SOURCE_BLOCK_0__-->          color: var(--pe-accent-text); background: var(--pe-accent-bg); border: 1px solid var(--pe-accent);
<!--__MDX_SOURCE_BLOCK_0__-->        }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-link:hover { filter: brightness(0.97); }
<!--__MDX_SOURCE_BLOCK_0__-->        .pe-link:focus-visible { outline: 2px solid var(--pe-accent); outline-offset: 2px; }
<!--__MDX_SOURCE_BLOCK_0__-->        @media (max-width: 700px) {
<!--__MDX_SOURCE_BLOCK_0__-->          .pe-head { padding: 16px 16px 14px; }
<!--__MDX_SOURCE_BLOCK_0__-->          .pe-body { flex-direction: column; }
<!--__MDX_SOURCE_BLOCK_0__-->          .pe-tree-pane { width: 100%; border-right: none; border-bottom: 1px solid var(--pe-border); }
<!--__MDX_SOURCE_BLOCK_0__-->          .pe-line-tree { display: none; }
<!--__MDX_SOURCE_BLOCK_0__-->          .pe-line-compact { display: flex; }
<!--__MDX_SOURCE_BLOCK_0__-->          .pe-panel { padding: 16px 16px 20px; }
<!--__MDX_SOURCE_BLOCK_0__-->        }
<!--__MDX_SOURCE_BLOCK_0__-->      `}</style>
<!--__MDX_SOURCE_BLOCK_0__-->
<!--__MDX_SOURCE_BLOCK_0__-->      <div>
<!--__MDX_SOURCE_BLOCK_0__-->        <div>
<!--__MDX_SOURCE_BLOCK_0__-->          <div>What goes in a plugin</div>
<!--__MDX_SOURCE_BLOCK_0__-->          <div>This example plugin, <code>my-plugin</code>, has one of every kind of component, each in its default location. Select a file or folder to read what it’s for and see what goes in it.</div>
<!--__MDX_SOURCE_BLOCK_0__-->        </div>
<!--__MDX_SOURCE_BLOCK_0__-->        <button type="button" onClick={toggleFullscreen} aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
<!--__MDX_SOURCE_BLOCK_0__-->          {isFullscreen ? '⤡' : '⛶'}
<!--__MDX_SOURCE_BLOCK_0__-->        </button>
<!--__MDX_SOURCE_BLOCK_0__-->      </div>
<!--__MDX_SOURCE_BLOCK_0__-->
<!--__MDX_SOURCE_BLOCK_0__-->      <div>
<!--__MDX_SOURCE_BLOCK_0__-->        <div>
<!--__MDX_SOURCE_BLOCK_0__-->          <div id="pe-tree-caption">Plugin directory</div>
<!--__MDX_SOURCE_BLOCK_0__-->          <div role="group" aria-labelledby="pe-tree-caption" onKeyDown={onTreeKeyDown}>
<!--__MDX_SOURCE_BLOCK_0__-->            <div><span>my-plugin/</span></div>
<!--__MDX_SOURCE_BLOCK_0__-->            {PIECES.map(p => <button key={p.id} id={'pe-node-' + p.id} type="button" aria-pressed={p.id === selected.id} aria-label={p.name + ', ' + p.path} onClick={() => setSelectedId(p.id)}>
<!--__MDX_SOURCE_BLOCK_0__-->                {p.lines.map((line, i) => <span key={i}>
<!--__MDX_SOURCE_BLOCK_0__-->                    {line.kind === 'folder' ?  : }
<!--__MDX_SOURCE_BLOCK_0__-->                    <span>{line.text}</span>
<!--__MDX_SOURCE_BLOCK_0__-->                    {p.required && i === p.lines.length - 1 ? <span>{p.required}</span> : null}
<!--__MDX_SOURCE_BLOCK_0__-->                  </span>)}
<!--__MDX_SOURCE_BLOCK_0__-->                <span>
<!--__MDX_SOURCE_BLOCK_0__-->                  
<!--__MDX_SOURCE_BLOCK_0__-->                  <span>{p.path}</span>
<!--__MDX_SOURCE_BLOCK_0__-->                  {p.required ? <span>{p.required}</span> : null}
<!--__MDX_SOURCE_BLOCK_0__-->                </span>
<!--__MDX_SOURCE_BLOCK_0__-->              </button>)}
<!--__MDX_SOURCE_BLOCK_0__-->          </div>
<!--__MDX_SOURCE_BLOCK_0__-->        </div>
<!--__MDX_SOURCE_BLOCK_0__-->
<!--__MDX_SOURCE_BLOCK_0__-->        <div role="region" aria-labelledby="pe-panel-caption" aria-live="polite" aria-atomic="true">
<!--__MDX_SOURCE_BLOCK_0__-->          <div id="pe-panel-caption">Selected piece</div>
<!--__MDX_SOURCE_BLOCK_0__-->          <div>{selected.name}{selected.required ? <span>{selected.required}</span> : null}</div>
<!--__MDX_SOURCE_BLOCK_0__-->          <div>{selected.path}</div>
<!--__MDX_SOURCE_BLOCK_0__-->
<!--__MDX_SOURCE_BLOCK_0__-->          <div>{children}</div>
<!--__MDX_SOURCE_BLOCK_0__-->
<!--__MDX_SOURCE_BLOCK_0__-->          <a href={selected.href}>{selected.linkText}</a>
<!--__MDX_SOURCE_BLOCK_0__-->        </div>
<!--__MDX_SOURCE_BLOCK_0__-->      </div>
<!--__MDX_SOURCE_BLOCK_0__-->    </div>;
<!--__MDX_SOURCE_BLOCK_0__-->};

A Claude Code plugin is built from components, such as skills, agents, hooks, and MCP servers. Each component has a default folder in the plugin, an optional manifest key in `.claude-plugin/plugin.json` that replaces or adds to that folder, and a name the user sees. For each key's full field table, see the [manifest reference](./manifest-reference.md#fields).

Use this page to add a component to a plugin that already loads.

After you add a component, run `/reload-plugins` in a running session or start a new one so Claude Code loads it. To check the component's file before loading it, run [`claude plugin validate .`](./cli-reference.md#plugin-validate) in your shell from the plugin directory.

> [!NOTE]
> These cases are covered on other pages:
>
> * **Building your first plugin**: start with [Create a plugin](./create.md)
> * **Installing someone else's plugin**: see [Install plugins](./install.md)
> * **Your plugin's users are on claude.ai or in Cowork**: a different set of components loads there. See [Plugins on claude.ai and in Cowork](https://claude.com/docs/plugins/overview)

## Explore the plugin directory

The explorer shows an example plugin, `my-plugin`, that has one of every kind of component in its default location:

* A review skill and an `about` command
* A security-review subagent
* A hook that formats files after Claude edits them, and the `scripts/` folder it calls
* A log monitor
* An output style and a color theme
* A route-audit workflow
* A `hello-plugin` executable
* Default settings
* A local MCP server and a Go language server

Each file is the smallest valid example of its format, there to show the shape rather than to be useful: a real skill or agent carries full instructions and often supporting files, and a real hook or monitor does real work. The sections after the explorer use the same files as their examples and link to fuller ones. Select a file or folder to read what it's for, see what goes in it, and find the section that covers it.

<PluginExplorer>
  <Piece id="manifest">
    The [manifest](./manifest-reference.md) is the `plugin.json` file in a plugin's `.claude-plugin/` directory. It contains the plugin's metadata and the `userConfig` values that Claude Code prompts the user for. Only `name` is required. In this one, `description` is the text users see for the plugin in `/plugin`, and `version` keeps users on that version until you change it:

    ```json theme={null}
    {
      "name": "my-plugin",
      "version": "1.0.0",
      "description": "Review, formatting, and database tools for this team"
    }
    ```
  </Piece>

  <Piece id="skills">
    A [skill](../skills.md) is a `SKILL.md` file. Save each skill in its own directory under `skills/`. Claude reads every skill's `description`, and when what the user asks for matches it, such as asking Claude to review a pull request here, Claude loads the skill's instructions and follows them. The user can also run it directly as `/my-plugin:review`:

    ```markdown theme={null}
    ---
    description: Reviews a pull request for style and test coverage. Use when asked to review code.
    ---

    Review the changed files. Report style problems first, then missing tests.
    ```
  </Piece>

  <Piece id="commands">
    A command is a single Markdown file the user runs by name. Commands are the older format: a skill runs by name the same way and can also carry supporting files in its own directory, so write new ones as skills and keep `commands/` for files you already have. This file becomes `/my-plugin:about` and takes the same frontmatter as a skill:

    ```markdown theme={null}
    ---
    description: Summarize the repository
    ---

    Summarize what this repository does in three sentences.
    ```
  </Piece>

  <Piece id="agents">
    A [subagent](../sub-agents.md) is a separate assistant, with its own instructions and its own context window, that Claude can delegate a task to and get a result back from. Each Markdown file under `agents/` defines one: the frontmatter names it and says when to use it, and the body is its system prompt. This one is named `my-plugin:security-reviewer`, and the user can invoke it with `@agent-my-plugin:security-reviewer`:

    ```markdown theme={null}
    ---
    name: security-reviewer
    description: Reviews code changes for security issues. Use after edits to authentication or input handling.
    model: sonnet
    ---

    You are a security reviewer. Read the changed files and report injection, authentication, and secrets-handling risks.
    ```
  </Piece>

  <Piece id="hooks">
    A [hook](../hooks-guide.md) runs something automatically at a point in Claude Code's lifecycle, such as after every file edit: a shell command, an HTTP request, an MCP tool call, a prompt to a model, or a subagent. Save the plugin's hooks in `hooks/hooks.json` at the plugin root. This one runs the plugin's `scripts/format.sh` after Claude writes or edits a file:

    ```json theme={null}
    {
      "hooks": {
        "PostToolUse": [
          {
            "matcher": "Write|Edit",
            "hooks": [
              {
                "type": "command",
                "command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/format.sh\""
              }
            ]
          }
        ]
      }
    }
    ```
  </Piece>

  <Piece id="monitors">
    A monitor is a shell command that Claude Code starts in the background when the session starts and keeps running until it ends, using the [Monitor tool](../tools-reference.md#monitor-tool). What it prints reaches Claude as notifications. A `when` field can instead start it the first time a named skill runs. This one tails an error log:

    ```json theme={null}
    [
      {
        "name": "error-log",
        "command": "tail -F ./logs/error.log",
        "description": "Application error log"
      }
    ]
    ```
  </Piece>

  <Piece id="output-styles">
    A plugin can include [output styles](../output-styles.md), which change how Claude formats and phrases its replies. Save each output style as `output-styles/<name>.md`. This one appears in `/output-style` as `my-plugin:terse`:

    ```markdown theme={null}
    ---
    name: terse
    description: Answer in as few words as possible
    keep-coding-instructions: true
    ---

    Keep every reply short. Skip preambles and summaries.
    ```
  </Piece>

  <Piece id="themes">
    A plugin can include [color themes](../terminal-config.md#create-a-custom-theme) for the Claude Code interface. Save each theme as `themes/<slug>.json`. This one appears in `/theme` as `Dracula`, marked as from `my-plugin`:

    ```json theme={null}
    {
      "name": "Dracula",
      "base": "dark",
      "overrides": {
        "claude": "#bd93f9",
        "error": "#ff5555"
      }
    }
    ```
  </Piece>

  <Piece id="workflows">
    The `workflows/` folder holds [workflow](../workflows.md) `.js` files: a `meta` block, then a script body that orchestrates several subagents. This one runs as `/my-plugin:audit-routes`:

    ```javascript theme={null}
    export const meta = {
      name: 'audit-routes',
      description: 'Audit every route handler for missing auth checks',
    }

    const found = await agent('List every .ts file under src/routes/.', {
      schema: { type: 'object', required: ['files'], properties: { files: { type: 'array', items: { type: 'string' } } } },
    })

    const audits = await pipeline(found.files, file =>
      agent(`Audit ${file} for missing authentication checks.`, { label: file }),
    )

    return audits.filter(Boolean)
    ```
  </Piece>

  <Piece id="bin">
    `bin/` is how a plugin ships a command-line tool. While the plugin is enabled, Claude Code puts this folder on the `PATH` of the shell it runs commands in, so Claude, or a skill's instructions, can run the tool by name without the user installing anything. With this [executable](#executables) in place, `hello-plugin` is a command Claude can run:

    ```bash theme={null}
    #!/bin/bash
    echo "hello from my-plugin"
    ```
  </Piece>

  <Piece id="scripts">
    The hook in `hooks/hooks.json` runs a script, and this folder is where the example keeps it. The name `scripts/` is a convention, not something Claude Code looks for: the hook points at the file by its path, `${CLAUDE_PLUGIN_ROOT}/scripts/format.sh`. A formatter script might look like this:

    ```bash theme={null}
    #!/bin/bash
    npx prettier --write .
    ```
  </Piece>

  <Piece id="settings">
    A `settings.json` at the plugin root holds [settings](../settings-reference.md) that apply while the plugin is enabled, so a plugin can change how the session behaves and not only add components. Only two keys take effect from a plugin, [`agent`](../settings-reference.md#agent) and [`subagentStatusLine`](../settings-reference.md#subagentstatusline); every other key is dropped. See [Default settings](#default-settings).

    This one sets `agent`, which runs the session's main thread as the plugin's own `security-reviewer` agent, so that agent's system prompt, tool restrictions, and model apply to the whole session:

    ```json theme={null}
    {
      "agent": "security-reviewer"
    }
    ```
  </Piece>

  <Piece id="mcp">
    An [MCP server](../mcp.md) gives Claude tools from an external system. Declare it in `.mcp.json` at the plugin root. This one starts a local server from a script inside the plugin, and appears in `/mcp` as `plugin:my-plugin:db`:

    ```json theme={null}
    {
      "mcpServers": {
        "db": {
          "command": "node",
          "args": ["${CLAUDE_PLUGIN_ROOT}/server.js"]
        }
      }
    }
    ```
  </Piece>

  <Piece id="lsp">
    An LSP server gives Claude [diagnostics and code navigation](./code-intelligence.md) for a language. Declare the server in `.lsp.json` at the plugin root. This one connects the Go language server for `.go` files:

    ```json theme={null}
    {
      "gopls": {
        "command": "gopls",
        "args": ["serve"],
        "extensionToLanguage": {
          ".go": "go"
        }
      }
    }
    ```
  </Piece>
</PluginExplorer>

## Add each kind of component

Each section below covers one kind of component: where its files go in the plugin, an example that validates, what the user sees once the plugin loads, and the manifest key that changes the default location. Add the ones your plugin needs; none is required.

### Skills

A [skill](../skills.md) is a `SKILL.md` file that Claude can load when its description matches the task. The user can also run it as a command. Save each skill in its own directory under `skills/`:

```text theme={null}
my-plugin/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── review/
        └── SKILL.md
```

Give the `SKILL.md` a `description` so Claude knows when to use it:

```markdown skills/review/SKILL.md theme={null}
---
description: Reviews a pull request for style and test coverage. Use when asked to review code.
---

Review the changed files. Report style problems first, then missing tests.
```

After you load the plugin, `/my-plugin:review` runs the skill. The command name and who can invoke it follow these rules:

* **Command name**: `/<plugin>:<directory>`, so `skills/review/SKILL.md` in `my-plugin` is `/my-plugin:review`. If you set `name` in the frontmatter, it replaces the last segment and the plugin prefix stays. See [how a skill gets its command name](../skills.md#how-a-skill-gets-its-command-name)
* **Who invokes it**: Claude, the user, or both, controlled by frontmatter. See [Control who invokes a skill](../skills.md#control-who-invokes-a-skill)

You can also place skills outside the default `skills/` directory:

* **Additional directories**: list them in the `skills` manifest key. They add to the default `skills/` scan rather than replacing it, unlike `commands` and `agents`
* **A single skill at the plugin root**: with no `skills/` directory and no `skills` manifest key, a `SKILL.md` at the plugin root loads as one skill. Set `name` in its frontmatter, because otherwise a marketplace install names the skill after its [cache directory](./loading.md#find-plugins-on-disk) rather than your plugin

To include instructions in a plugin, write them as a skill. Claude Code doesn't load a `CLAUDE.md` at the plugin root, and `claude plugin validate` warns `CLAUDE.md at the plugin root is not loaded as project context`.

For frontmatter fields and supporting files, see [Skills](../skills.md).

### Commands

A command is a single Markdown file the user runs by name, such as `/my-plugin:about`.

> [!NOTE]
> Commands are the older format, and [skills](#skills) supersede them for new work. A skill runs by name the same way, and it can also carry supporting files in its directory. Keep `commands/` for files you're moving over from `.claude/commands/`.

Save a command at `commands/<file>.md` and it becomes `/<plugin>:<file>`. A subdirectory adds a segment, so `commands/db/migrate.md` is `/my-plugin:db:migrate`.

Command files take the same frontmatter as skills.

#### Define commands in the manifest

You only need this if you want to keep command files somewhere other than `commands/`, or to define a short command inside `plugin.json` without a separate Markdown file. Set the `commands` manifest key, and Claude Code reads it instead of scanning `commands/`. The key takes a path, an array of paths, or an object that maps each command name to either a `source` file or inline `content`.

This manifest defines `/my-plugin:about` inline, with no Markdown file:

```json .claude-plugin/plugin.json theme={null}
{
  "name": "my-plugin",
  "commands": {
    "about": {
      "content": "Summarize what this repository does in three sentences.",
      "description": "Summarize the repository"
    }
  }
}
```

Load the plugin and run `/my-plugin:about` in the session to confirm it loaded.

For the full key syntax, see [`commands`](./manifest-reference.md#commands).

### Agents

A [subagent](../sub-agents.md) is a separate assistant, with its own instructions and context window, that Claude can delegate a task to. Each Markdown file under `agents/` defines one:

```markdown agents/security-reviewer.md theme={null}
---
name: security-reviewer
description: Reviews code changes for security issues. Use after edits to authentication or input handling.
model: sonnet
---

You are a security reviewer. Read the changed files and report injection, authentication, and secrets-handling risks.
```

This agent is named `my-plugin:security-reviewer`, and the user can [invoke it explicitly](../sub-agents.md#invoke-subagents-explicitly) with `@agent-my-plugin:security-reviewer`. The name form is `<plugin>:<name>`, where `<name>` comes from the frontmatter, or from the file name when there is none.

The `agents` manifest key replaces the `agents/` scan.

#### Organize agents in subfolders

You can put plugin agent files in subfolders of `agents/`. Claude Code [loads them recursively](../sub-agents.md#choose-the-subagent-scope) and joins the plugin name, each subfolder name, and the file name with colons to form the agent's scoped name. For example, `agents/review/security.md` in a plugin named `my-plugin` loads as `my-plugin:review:security`. Two settings change that name:

* Frontmatter `name`: it replaces only the file name, so `name: audit` in `agents/review/security.md` loads as `my-plugin:review:audit`
* Manifest [`agents`](./manifest-reference.md#fields) field: a file you list there loads without subfolder names, so `"agents": "./custom/review/security.md"` loads as `my-plugin:security`

#### Frontmatter fields in plugin agents

A plugin agent's frontmatter follows these rules:

* **Supported fields**: `name`, `description`, `model`, `effort`, `maxTurns`, `tools`, `disallowedTools`, `skills`, `memory`, `background`, `omitClaudeMd`, `isolation`, `color`, and the `cacheTtl` key of `experimental`. The only valid `isolation` value is `"worktree"`. See [supported frontmatter fields](../sub-agents.md#supported-frontmatter-fields) for what each one does
* **Ignored fields**: `permissionMode`, `hooks`, `mcpServers`, and `initialPrompt`. An agent file can't add hooks or MCP servers on its own, so add those as plugin [hooks](#hooks) and [MCP servers](#mcp-servers) instead
* **Frontmatter that doesn't parse**: the agent still loads with every field ignored. It's named after the file, and its description reads `Agent from my-plugin plugin`. Run [`claude plugin validate`](./cli-reference.md#plugin-validate) in your shell to find these files

For what each field does and the precedence rules, see [Subagents](../sub-agents.md#supported-frontmatter-fields).

### Hooks

A [hook](../hooks-guide.md) runs something automatically at a point in Claude Code's lifecycle, such as after every file edit: a shell command, an HTTP request, an MCP tool call, a prompt to a model, or a subagent. Save the plugin's hooks in `hooks/hooks.json` at the plugin root, under a top-level `"hooks"` key, in the same shape as the `hooks` object in `settings.json`. That lets you copy an existing settings hook in unchanged.

This hook runs a bundled script after every `Write` or `Edit`:

```json hooks/hooks.json theme={null}
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/format.sh\""
          }
        ]
      }
    ]
  }
}
```

Save the script at `scripts/format.sh` and make it executable.

Load the plugin and ask Claude to edit a file. A `PostToolUse` hook that exits 0 shows nothing in the transcript, so confirm it ran with [debug logging](../hooks.md#debug-hooks) or by what the script itself changes.

Hooks in `hooks/hooks.json` and in the `hooks` manifest key both load. For every event and its payload, see [Hook events](../hooks.md#hook-events).

#### When plugin hooks fire

A plugin's hooks don't wait for one of the plugin's skills or commands to be used. Claude Code registers them when a session loads the plugin, and they fire on their events from then on. To limit when a hook runs, narrow its `matcher`.

If a hook never fires, see [hooks that don't fire](./troubleshooting.md#failed-to-load-hooks-from-and-hooks-that-dont-fire).

#### Environment, quoting, and matching MCP tools

The hook's environment, the quoting of `${CLAUDE_PLUGIN_ROOT}`, and matchers for the plugin's own MCP tools work as follows:

* **Environment**: every hook process receives `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` in its environment, plus `CLAUDE_PLUGIN_OPTION_<KEY>` for each [user configuration](#user-configuration) value, so your script can read them from there
* **Quoting**: when `command` has no `args`, it runs through a shell, so wrap the `${CLAUDE_PLUGIN_ROOT}` path in double quotes, as the `hooks/hooks.json` example under [Hooks](#hooks) does, to keep the expanded path one shell word. When you pass `args` instead, each element is passed as one argument with no shell and needs no quoting. See [exec form and shell form](../hooks.md#exec-form-and-shell-form)
* **Matching the plugin's own MCP tools**: a tool from an [MCP server this plugin declares](#mcp-servers) is named `mcp__plugin_<plugin>_<server>__<tool>`, so write that full name in the matcher. A matcher on the server name alone never fires. See [Match MCP tools](../hooks.md#match-mcp-tools)

### MCP servers

An MCP server gives Claude tools from an external system. Declare it in `.mcp.json` at the plugin root, in the same shape as a [project `.mcp.json`](../mcp.md#project-scope). This `.mcp.json` declares one server named `db`:

```json .mcp.json theme={null}
{
  "mcpServers": {
    "db": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/server.js"]
    }
  }
}
```

You can also omit the `mcpServers` wrapper and put `db` at the top level of the file.

Load the plugin and run `/mcp` to confirm the server appears as `plugin:my-plugin:db`.

`claude plugin validate` checks `.mcp.json` and reports a server entry that Claude Code would drop at load time as an error. Requires Claude Code v2.1.281 or later.

For where a bad entry shows up at load time, see [MCP servers that don't start](./troubleshooting.md#invalid-mcp-server-config-for-and-mcp-servers-that-dont-start).

The `mcpServers` manifest key takes an inline server map, a path to a JSON file, or an array of those. When a manifest server has the same name as one in `.mcp.json`, the manifest server replaces it.

#### Reach users on claude.ai and Cowork

A local stdio server, such as the `db` server under [MCP servers](#mcp-servers), runs in Claude Code and in a Cowork session that runs on your machine in the Claude Desktop app, but not on claude.ai. To reach users there too, reference a remote server by its `https://` URL, which claude.ai and Cowork offer to the user as a connector.

#### Server names, tool names, and reloads

The server's names, variable substitution, and reload behavior follow these rules:

* **Server name**: `plugin:<plugin>:<server>`, so the `db` server in `my-plugin` is `plugin:my-plugin:db` in `/mcp`. Use the same form to name the server in an [`mcp_tool` hook](../hooks.md#mcp-tool-hook-fields)
* **Tool names**: `mcp__plugin_<plugin>_<server>__<tool>`, so a `query` tool on that `db` server is `mcp__plugin_my-plugin_db__query`. That is the name to use in [permission rules](../permissions.md) and [hook matchers](#hooks)
* **Substitution**: `${CLAUDE_PLUGIN_ROOT}` and the other [path variables](#path-variables-and-persistent-data) are substituted in `command`, `args`, and `env`. No quoting is needed in `args`, because each element is passed as one argument
* **Reload**: when the user runs `/reload-plugins` and [the reload applies](./cli-reference.md#reloads-that-change-mcp-tools), a server whose configuration is unchanged keeps its connection. A server whose configuration changed reconnects, and one you removed disconnects

#### Include a packaged MCPB server

The `mcpServers` key also accepts a packaged server as an [MCPB file](https://github.com/modelcontextprotocol/mcpb), whose extension is `.mcpb` or the older `.dxt`. Point the key at the file, as a path inside the plugin or an `https://` URL:

```json .claude-plugin/plugin.json theme={null}
{
  "name": "my-plugin",
  "mcpServers": "./servers/db.mcpb"
}
```

The server takes its name from the `name` in the bundle's manifest.

For transports and authentication, see [MCP](../mcp.md#plugin-provided-mcp-servers).

### LSP servers

An LSP server gives Claude diagnostics and code navigation for a language. If an [official code intelligence plugin](./code-intelligence.md) already covers your language, install that instead of writing one. Otherwise declare the server in `.lsp.json` at the plugin root:

```json .lsp.json theme={null}
{
  "gopls": {
    "command": "gopls",
    "args": ["serve"],
    "extensionToLanguage": {
      ".go": "go"
    }
  }
}
```

The file maps each server name directly to its configuration, with no wrapper object around the map. `command` is the binary's name, with its arguments in `args`. `extensionToLanguage` needs at least one extension, each starting with `.`.

`claude plugin validate` doesn't read this file. When any entry is invalid, the whole file is skipped at load and `Invalid LSP server config for ".lsp.json"` appears in the `/plugin` **Errors** tab.

Your plugin configures the connection but doesn't install the server binary, and each file extension gets one server:

* **Missing binary**: Claude Code starts `command` by name from the user's `PATH`. When the binary isn't there, the server fails to start and `claude --debug` logs `LSP server <name> failed to start`
* **Extension conflicts**: when two enabled servers claim the same extension, the first registered handles those files and the other isn't used for them, whether the servers come from one plugin or two. The `/plugin` **Errors** tab shows the warning `LSP server "<name>" is not used for <ext> files`

The `lspServers` manifest key takes the same map inline, a path to a JSON file, or an array of those, and its servers add to the ones in `.lsp.json`. When a manifest server has the same name as one in `.lsp.json`, the manifest server replaces it.

For `transport`, timeouts, restarts, and the other fields, see [`lspServers`](./manifest-reference.md#lspservers).

Send log output to stderr, not stdout. Claude Code reads a server's stdout as protocol messages only, and accepts message headers up to 64 KiB and a message body up to 32 MiB.

Claude Code disconnects a server that exceeds either limit or writes non-protocol output to stdout, and counts the disconnect as a crash for `restartOnCrash` and `maxRestarts`. When you run with `--debug`, Claude Code writes an error naming the cause to the debug log.

### Executables

Files in `bin/` at the plugin root are on the `PATH` of the Bash tool's shell while the plugin is enabled, so Claude can run them as bare commands. Add an executable script:

```bash bin/hello-plugin theme={null}
#!/bin/bash
echo "hello from my-plugin"
```

Make it executable with `chmod +x bin/hello-plugin` and load the plugin. When you ask Claude to run `hello-plugin`, the Bash tool result shows the script's output.

Plugin `bin/` directories come after the user's own `PATH` entries, so a plugin can't shadow `git`, `ls`, or another system command.

claude.ai and Cowork don't install a plugin that has a top-level `bin/` directory, including one you [distribute through claude.ai organization settings](./host-marketplace.md#distribute-through-organization-settings).

### Default settings

To set defaults that apply while the plugin is enabled, add a `settings.json` at the plugin root, or put the same object inline in the `settings` manifest key. Two keys take effect, `agent` and `subagentStatusLine`, and every other key is dropped.

Set `agent` to run one of the plugin's own agents as the main thread:

```json settings.json theme={null}
{
  "agent": "security-reviewer"
}
```

Load the plugin and start a session. Claude then answers in the main conversation with the `security-reviewer` agent's system prompt and model.

For everything the key controls, see the [`agent` setting](../settings-reference.md#agent).

When the same key is set in more than one place, these rules decide which value applies:

* **File over manifest**: when both exist and `settings.json` sets at least one supported key, `settings.json` applies and the manifest's `settings` is ignored
* **User settings over plugin defaults**: across settings sources, plugin defaults are the lowest layer, so a user's own `agent` in `~/.claude/settings.json` overrides yours
* **Two plugins set the same key**: the value from the plugin loaded last applies, and `claude --debug` logs `overrides setting`

For the `subagentStatusLine` shape, see [subagent status lines](../statusline.md#subagent-status-lines).

### Themes and output styles

A plugin can include color themes and output styles. Both appear in the same pickers as the user's own. For either one, setting the manifest key replaces the folder scan.

| Component    | Save as                   | Format                                                                                                                      | Appears in                            | Manifest key          |
| :----------- | :------------------------ | :-------------------------------------------------------------------------------------------------------------------------- | :------------------------------------ | :-------------------- |
| Theme        | `themes/<slug>.json`      | The [custom theme file](../terminal-config.md#create-a-custom-theme) format users write in `~/.claude/themes/`                | `/theme`, under the file's `name`     | `experimental.themes` |
| Output style | `output-styles/<name>.md` | The [custom output style](../output-styles.md#create-a-custom-output-style) format, with `name` and `description` frontmatter | `/output-style`, as `<plugin>:<name>` | `outputStyles`        |

Plugin themes are read-only, so when a user edits one in `/theme`, the edit is saved as a copy in their own themes directory.

This theme recolors the prompt accent and error text on the dark preset:

```json themes/dracula.json theme={null}
{
  "name": "Dracula",
  "base": "dark",
  "overrides": {
    "claude": "#bd93f9",
    "error": "#ff5555"
  }
}
```

### Channels

A [channel](../channels.md) lets an outside system such as a chat app send messages into a session. In a plugin, a channel is one of the MCP servers plus a `channels` entry that binds to it and can prompt for its own configuration. This manifest binds a channel to a `telegram` server and asks for a bot token:

```json .claude-plugin/plugin.json theme={null}
{
  "name": "my-plugin",
  "mcpServers": {
    "telegram": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/server.js"],
      "env": { "BOT_TOKEN": "${user_config.bot_token}" }
    }
  },
  "channels": [
    {
      "server": "telegram",
      "userConfig": {
        "bot_token": {
          "type": "string",
          "title": "Bot token",
          "description": "Telegram bot token",
          "sensitive": true
        }
      }
    }
  ]
}
```

`server` must match a key in `mcpServers`. The per-channel `userConfig` takes the same shape as the [top-level `userConfig` key](#user-configuration).

For what the server must implement and how users enable a channel plugin, see [Package as a plugin](../channels-reference.md#package-as-a-plugin) in the channels reference. For the field table, see [`channels`](./manifest-reference.md#channels).

### Monitors

A monitor is a shell command that runs in the background for the whole session. What it prints reaches Claude as notifications, so Claude can react to a log or a status change without being asked to watch it. Save the entries in `monitors/monitors.json`:

```json monitors/monitors.json theme={null}
[
  {
    "name": "error-log",
    "command": "tail -F ./logs/error.log",
    "description": "Application error log"
  }
]
```

The command runs in a shell, in the working directory the session started in.

A monitor's command is limited in where it starts and what it can reference:

* **Interactive sessions only**: plugin monitors start in an interactive session and never in non-interactive mode with the `-p` flag. They also start only where the [Monitor tool](../tools-reference.md#monitor-tool) is available
* **No user configuration**: `command` gets the [path variables](#path-variables-and-persistent-data) and `${ENV_VAR}` from the environment, but never `${user_config.*}`. A monitor that references one doesn't start, and monitor processes don't receive `CLAUDE_PLUGIN_OPTION_<KEY>` either
* **Disabling mid-session**: if you disable a plugin mid-session, Claude Code doesn't stop monitors that are already running. They stop when the session ends

The `experimental.monitors` manifest key takes the same array inline or a path to a JSON file, and is read instead of `monitors/monitors.json`.

For the `when` trigger and the other fields, see [`monitors`](./manifest-reference.md#monitors).

<h2 id="user-configuration">
  Ask the user for configuration values
</h2>

Declare the values your plugin needs from the user in the `userConfig` manifest key, so users don't edit `settings.json` themselves. Each option appears in a dialog with its `title` as the label and its `description` beneath it.

Set `"sensitive": true` for a token or password. The dialog then masks the input, and the value is stored in secure storage rather than `settings.json`.

This manifest asks for an endpoint and a token:

```json .claude-plugin/plugin.json theme={null}
{
  "name": "my-plugin",
  "userConfig": {
    "api_url": {
      "type": "string",
      "title": "API URL",
      "description": "Base URL of your team's API"
    },
    "api_token": {
      "type": "string",
      "title": "API token",
      "description": "Token for your team's API",
      "sensitive": true
    }
  }
}
```

### When the configuration dialog appears

The dialog appears only in the interactive `/plugin` interface. It opens for any option that isn't set yet when the user does any of the following:

* Installs the plugin in `/plugin`
* Runs `/plugin install <plugin>@<marketplace>` inside a session
* Enables the plugin from the **Installed** tab in `/plugin`

To open the same dialog at any time, the user runs `/plugin configure <plugin>@<marketplace>`.

The `claude plugin install` shell command never prompts for `userConfig` values. To set values from the shell, pass each one as `--config KEY=VALUE`. When options remain unset, the command prints a `userConfig options not yet set` line that names both ways to set them. [The `userConfig` dialog never appears](./troubleshooting.md#the-userconfig-dialog-never-appears) quotes the line.

For the option fields, where each value is stored, how a component references a saved value, and which fields reject `${user_config.*}`, see [User configuration](./manifest-reference.md#user-configuration).

<h2 id="path-variables-and-persistent-data">
  Reference plugin paths and store data
</h2>

You don't know where your plugin will be installed, so refer to its files and data through these variables rather than fixed paths. They're substituted in skill, command, and agent content, in hook and monitor commands, and in MCP and LSP server configurations. They're also exported to hook, MCP, and LSP processes:

* **`${CLAUDE_PLUGIN_ROOT}`**: the plugin's install directory. Each version has its own [cache directory](./loading.md#find-plugins-on-disk), so the path changes when the plugin updates. Don't write state there
* **`${CLAUDE_PLUGIN_DATA}`**: a directory that survives updates, for `node_modules`, virtual environments, and caches. It resolves to `~/.claude/plugins/data/<id>/` and is created when first referenced
* **`${CLAUDE_PROJECT_DIR}`**: the project root, the same value hooks receive

In the data directory path, `<id>` is the plugin identifier with every character other than letters, digits, `_`, and `-` replaced by `-`, so `my-plugin@my-marketplace` becomes `my-plugin-my-marketplace`.

On Windows, the substituted paths use forward slashes so a shell doesn't read backslashes as escapes.

### Install dependencies into the data directory

For a marketplace-installed plugin, Claude Code installs eligible [Node.js package dependencies](./loading.md#node-js-package-dependencies) automatically when it caches the plugin, so you may not need to install them yourself. When you do, this `SessionStart` hook installs `node_modules` into `${CLAUDE_PLUGIN_DATA}` on first run and again after an update changes `package.json`:

```json hooks/hooks.json theme={null}
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "diff -q \"${CLAUDE_PLUGIN_ROOT}/package.json\" \"${CLAUDE_PLUGIN_DATA}/package.json\" >/dev/null 2>&1 || (cd \"${CLAUDE_PLUGIN_DATA}\" && cp \"${CLAUDE_PLUGIN_ROOT}/package.json\" . && npm install) || rm -f \"${CLAUDE_PLUGIN_DATA}/package.json\""
          }
        ]
      }
    ]
  }
}
```

After the first session, `~/.claude/plugins/data/<id>/node_modules` exists. An MCP server can then set `NODE_PATH` to `${CLAUDE_PLUGIN_DATA}/node_modules` in its `env`. For which fields substitute which variable, see [Environment variables](./manifest-reference.md#environment-variables).

## Next steps

* [Plugin manifest reference](./manifest-reference.md): `plugin.json` fields, path rules, and the standard layout
* [Test plugins with evals](../plugin-evals.md): check that the components you added change Claude's behavior the way you intend
* [Publish and distribute a plugin](./publish.md): version the plugin and put it in a marketplace
* [Troubleshoot plugins](./troubleshooting.md): what to do when a component doesn't load or a hook doesn't fire
