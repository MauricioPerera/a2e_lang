# a2e-lang VSCode Extension

Syntax highlighting for `.a2e` files — the DSL for the [A2E protocol](https://github.com/MauricioPerera/a2e).

## Features

- Syntax highlighting for all 16 operation types
- Keyword highlighting (`workflow`, `run`, `from`, `where`, `if`, `then`, `else`, `credential`)
- Path highlighting (`/workflow/data`)
- Comment support (`# comment`)
- Bracket matching and auto-closing
- Code folding for operation blocks

## Installation

### From source (development)

1. Copy the `vscode-extension` folder to your VSCode extensions directory:
   ```bash
   # Windows
   cp -r vscode-extension %USERPROFILE%\.vscode\extensions\a2e-lang

   # macOS/Linux
   cp -r vscode-extension ~/.vscode/extensions/a2e-lang
   ```

2. Restart VSCode

3. Open any `.a2e` file — syntax highlighting will activate automatically

### Using VSIX (optional)

```bash
cd vscode-extension
npx -y @vscode/vsce package
code --install-extension a2e-lang-0.1.0.vsix
```

## Highlighting Preview

| Element | Color (typical dark theme) |
|---|---|
| `workflow`, `run` | Purple (keyword) |
| `ApiCall`, `FilterData`, etc. | Green (type) |
| Operation IDs (`fetch`, `filter`) | Yellow (function) |
| `from`, `where`, `if`, `then`, `else` | Purple (keyword) |
| `/workflow/data` | Cyan (variable/path) |
| `"strings"` | Orange (string) |
| `42`, `3.14` | Light green (number) |
| `true`, `false`, `null` | Blue (constant) |
| `==`, `>`, `contains` | Red (operator) |
| `# comments` | Gray (comment) |
| `key:` (properties) | White (variable) |
