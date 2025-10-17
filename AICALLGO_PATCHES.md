# AiCallGo Pipecat Patches

## Overview

This is a **temporary fork** of [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) maintained by the AiCallGo team. It contains critical bug fixes needed for our production environment that are not yet available in the upstream project.

**Base Version**: v0.0.90
**Fork Purpose**: Fix race condition in Gemini Live function calling
**Expected Duration**: Temporary until upstream merges fix

---

## Current Patches

### 1. Gemini Live Function Calling Race Condition Fix

**File**: `src/pipecat/services/google/gemini_live/llm.py`
**Issue**: Tool/function results not being sent to Gemini Live API due to race condition
**Root Cause**: Audio processing triggers function calls instantly (~0ms), but speech-to-text transcription takes 300-800ms, causing user messages to arrive after tool results in the context

**Changes Made**:
1. Added Set-based tracking (`_sent_tool_results: Set[str]`) to track which tool results have been sent
2. Replaced simple last-message check with comprehensive scan of ALL messages in `process_frame()`
3. Mark tool results as sent after successful transmission in `_tool_result()`
4. Clear tracking state on connect/disconnect to prevent memory leaks

**Lines Modified**:
- Line ~640: Added `_sent_tool_results` Set initialization in `__init__`
- Lines 874-897: Comprehensive message scanning in `process_frame()`
- Lines 1318-1322: Mark tool results as sent in `_tool_result()`
- Lines 955-957: Clear tracking on connect in `_connect()`
- Lines 1170-1172: Clear tracking on disconnect in `_disconnect()`

**Documentation**: See `/Users/blickt/Documents/src/aicallgo-aiagent/docs/gemini_live_pipecat_support/function_calling_race_condition.md` for detailed root cause analysis.

---

## Fork Setup & Workflow

### Initial Setup (One-time)

1. **Fork the pipecat repository on GitHub**
   ```bash
   # Go to https://github.com/pipecat-ai/pipecat
   # Click "Fork" → Create under your organization (e.g., aicallgo/pipecat)
   ```

2. **Create and push patch branch**
   ```bash
   cd pipecat-source

   # Create branch based on current version
   git checkout -b aicallgo-patches

   # Commit the changes (already made)
   git add src/pipecat/services/google/gemini_live/llm.py
   git commit -m "fix: Gemini Live function calling race condition

   - Add Set-based tracking for sent tool results
   - Replace last-message check with comprehensive scan
   - Ensure tool results are sent even when user messages arrive out of order
   - Clear tracking state on connect/disconnect

   Fixes race condition where audio processing completes before STT transcription,
   causing tool results to not be sent to the LLM."

   # Add your fork as remote
   git remote add aicallgo https://github.com/YOUR-ORG/pipecat.git

   # Push the branch
   git push aicallgo aicallgo-patches
   ```

3. **Update parent repo submodule configuration**
   ```bash
   cd /Users/blickt/Documents/src/aicallgo-aiagent

   # Edit .gitmodules to point to your fork
   # Change:
   #   url = https://github.com/pipecat-ai/pipecat.git
   # To:
   #   url = https://github.com/YOUR-ORG/pipecat.git
   #   branch = aicallgo-patches

   # Sync submodule configuration
   git submodule sync
   git submodule update --remote

   # Commit the submodule update
   git add .gitmodules pipecat-source
   git commit -m "chore: use AiCallGo pipecat fork with race condition fix"
   git push
   ```

### Team Member Setup

When team members clone the main repo:
```bash
git clone https://github.com/YOUR-ORG/aicallgo-aiagent.git
cd aicallgo-aiagent
git submodule update --init --recursive
```

The submodule will automatically check out your forked version with the patches.

---

## Syncing with Upstream

When pipecat releases a new version you want to adopt:

```bash
cd pipecat-source

# Add upstream if not already added
git remote add upstream https://github.com/pipecat-ai/pipecat.git

# Fetch latest upstream changes
git fetch upstream

# Check out your patch branch
git checkout aicallgo-patches

# Rebase your patches on top of the new upstream version
# Replace vX.X.XX with the new version tag
git rebase upstream/vX.X.XX

# Test thoroughly to ensure patches still work!
# Then force push (since rebase rewrites history)
git push aicallgo aicallgo-patches --force-with-lease

# Update parent repo to use new version
cd ..
git add pipecat-source
git commit -m "chore: update pipecat to vX.X.XX with rebased patches"
git push
```

---

## Switching Back to Upstream

When the upstream pipecat project fixes this issue:

1. **Verify the fix is in upstream**
   ```bash
   # Check upstream changelog/commits
   # Test with official version to confirm fix works
   ```

2. **Update .gitmodules back to official repo**
   ```bash
   cd /Users/blickt/Documents/src/aicallgo-aiagent

   # Edit .gitmodules:
   # Change back to:
   #   url = https://github.com/pipecat-ai/pipecat.git
   # Remove:
   #   branch = aicallgo-patches

   git submodule sync
   git submodule update --remote

   git add .gitmodules pipecat-source
   git commit -m "chore: switch back to official pipecat (upstream fixed race condition)"
   git push
   ```

3. **Archive your fork** (optional)
   - Keep the fork repository archived on GitHub for reference
   - Add a note in the fork's README that it's been merged upstream

---

## Important Notes

- **Never commit directly to `main`/`master` in the fork** - always use the `aicallgo-patches` branch
- **Document all patches** in this file when adding new ones
- **Test thoroughly** after syncing with upstream - patches may need adjustments
- **Keep fork private** if it contains any proprietary modifications (not applicable for this bug fix)
- **Monitor upstream issues** - track if/when they fix the race condition so we can switch back

---

## Related Documentation

- Root cause analysis: `/Users/blickt/Documents/src/aicallgo-aiagent/docs/gemini_live_pipecat_support/function_calling_race_condition.md`
- Upstream pipecat docs: https://docs.pipecat.ai
- Our main repo: `/Users/blickt/Documents/src/aicallgo-aiagent/`

---

**Last Updated**: October 17, 2025
**Maintainer**: AiCallGo Engineering Team
