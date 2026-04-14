# Contributing to Aguia

Thank you for your interest in contributing to Aguia! This guide will help you get started.

## Reporting Issues

- Use [GitHub Issues](https://github.com/BrunoPessoa22/aguia/issues)
- Include: what you expected, what happened, your OS, and Claude Code CLI version (`claude --version`)
- For agent template suggestions, use the "Agent Idea" label

## Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Test locally (see below)
5. Commit with conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
6. Push and open a PR against `main`

### Commit Style

- Conventional commits: `feat: add newsletter agent template`
- Imperative mood, 50-char summary max
- Optional body explains WHY, not WHAT
- No debug code, console.logs, or commented-out blocks

### PR Checklist

- [ ] Tested locally (dispatched the agent, ran the script)
- [ ] No personal info (API keys, emails, company names, family names)
- [ ] CLAUDE.md templates use `[YOUR NAME]`, `[YOUR COMPANY]` placeholders
- [ ] Scripts pass shellcheck (`shellcheck orchestrator/*.sh`)
- [ ] Updated README.md if behavior changed

## Code Style

### Bash Scripts
- Use `shellcheck` for linting: `shellcheck orchestrator/*.sh scripts/*.sh`
- Use `set -euo pipefail` at the top of scripts
- Quote all variables: `"$VAR"` not `$VAR`
- Use `[[ ]]` for conditionals, not `[ ]`

### Python
- Format with `black` and `isort`
- Type hints on all function signatures
- No bare `except:` -- always catch specific exceptions

### Markdown
- Format with `prettier` if available
- Use `--` (double dash) for em-dashes, not unicode characters
- Keep lines under 100 characters where practical

## How to Add a New Agent Template

1. Create the agent directory:
   ```bash
   ./agents/create-agent.sh my-agent "What this agent does"
   ```

2. Edit `agents/my-agent/CLAUDE.md` with a complete, well-documented template

3. Sanitize all personal information:
   - Replace names with `[YOUR NAME]`
   - Replace companies with `[YOUR COMPANY]`
   - Replace URLs with `[YOUR URL]`
   - Replace API keys with `[YOUR_API_KEY]`

4. Add the agent to the Agent Gallery table in `README.md`

5. Add a brief entry to `examples/agent-fleet.md`

6. Submit a PR with:
   - The new agent template
   - Updated README.md gallery
   - Updated examples/agent-fleet.md

## How to Add a New Integration

1. Create a directory under `integrations/your-integration/`
2. Include a README.md with:
   - Prerequisites and dependencies
   - Step-by-step setup instructions
   - Environment variables needed
   - Example dispatch.sh routing configuration
3. Add any scripts needed for the integration
4. Update the main README.md to mention the integration
5. Submit a PR

## Testing Locally

```bash
# Test the dispatcher with a simple prompt
./orchestrator/dispatch.sh example-agent "Hello! Introduce yourself and write a log."

# Check the output
cat shared/logs/example-agent_$(date +%Y-%m-%d).log

# Test agent scaffolding
./agents/create-agent.sh test-agent "A test agent"
ls agents/test-agent/
rm -rf agents/test-agent/  # cleanup

# Lint bash scripts
shellcheck orchestrator/*.sh scripts/*.sh agents/create-agent.sh install.sh
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
