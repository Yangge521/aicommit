# Shell Completion Scripts

This directory contains shell completion scripts for aicommit.
Generate fresh scripts with `aicommit --completion <shell>`.

## Installation

### Bash
```bash
# Generate and save:
aicommit --completion bash > ~/.aicommit-completion.bash
echo 'source ~/.aicommit-completion.bash' >> ~/.bashrc
```

### Zsh
```bash
aicommit --completion zsh > ~/.aicommit-completion.zsh
echo 'source ~/.aicommit-completion.zsh' >> ~/.zshrc
```

### Fish
```fish
aicommit --completion fish > ~/.config/fish/completions/aicommit.fish
```

### PowerShell
```powershell
aicommit --completion powershell > $PROFILE.CurrentUserAllHosts
# Or add to your profile:
aicommit --completion powershell | Out-String | Invoke-Expression
```
