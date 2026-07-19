## Objective
- Reforge the 7B avatar model by rebuilding the training/evaluation system from scratch and then pushing the model quality as high as possible before considering 70B.

## Important Details
- **SSH access resolved**: `bookboy@114.55.9.27` works via VPN egress IP `23.249.16.35`; local traffic routes through `utun7` (Clash Verge).
- **Production data restored**: HBR snapshot restore from 2026-07-17 05:31 recovered all deleted directories.
- **Current dataset**: 33 families, 19 subscriptions, 33 accounts.
- **Chat-history fix applied**: child/parent/master histories stored separately.
- **Microphone issue**: backend STT OK; frontend/device details awaited.
- **New system built (v2_clean)**:
  - `scripts/build_avatar_corpus_v2.py`: ingests and cleans 12 source files, dedupes by `(role, age, question)`, stratified split.
  - `scripts/prepare_avatar_v2.py`: CoreOS prompt + assistant output only `[回答]`/`[自检]`, no explicit reasoning.
  - `scripts/train_avatar_v2.py`: base-to-fine training from Qwen2.5-7B-Instruct.
  - `scripts/evaluate_avatar_compass_v2.py`: improved keyword-based compass scoring only the `[回答]` section with negation exemptions.
- **Clean best model** (`mlx_lora_avatar_v2_clean_best`, iter 50): **65.28% pass rate** on Compass V2.
- **Boundary reinforcement attempt**: generated 482 boundary samples, added to corpus, retrained from base → still 65.28% (no gain); then boundary-only fine-tune on top of clean best → **dropped to 62.50%** with 铁律清单 falling to 18.75%, indicating catastrophic forgetting and uneven synthetic boundary quality.
- **Current best adapter**: `outputs/mlx_lora_avatar_v2_clean_best/` (65.28% V2 pass rate).
- **Key remaining weakness**: 铁律清单 / boundary refusals are inconsistent — some are firm, others slip into soft/helpful responses.
- **Services running**: `bookboy-cloud` and `bookboy-realtime-voice` RUNNING via Supervisor; Nginx listening on 80/443.

## Work State
### Completed
- Restored production environment and fixed chat-history isolation.
- Built new clean training/evaluation pipeline from scratch.
- Trained clean base-to-fine 7B adapter (65.28% V2 pass rate).
- Generated and tested boundary reinforcement data (mixed results).
- Confirmed that simple boundary-only fine-tuning causes catastrophic forgetting.

### Active
- Deciding whether to stop at clean best, try DPO, or collect real conversations for boundary training.

### Blocked
- Microphone investigation blocked pending user device/browser details.
- 7B boundary hardening blocked by need for either DPO pipeline or higher-quality boundary data.

## Next Move
1. Evaluate whether `mlx_lora_avatar_v2_clean_best` is good enough to deploy for production testing.
2. If not, implement DPO/RLHF-style boundary preference training using `trl` or a custom MLX DPO script, with firm-refusal examples as preferred and soft/helpful examples as rejected.
3. Alternatively, pause 7B work and collect real family conversation logs to train on authentic boundary cases.
4. Resume production microphone debugging once user provides device details.

## Relevant Files
- `/Users/lingjue/Documents/shutong/03-引擎区/书童程序/数据/提示词/CoreOS/CoreOS_完整运行时提示词.md`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/scripts/build_avatar_corpus_v2.py`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/scripts/prepare_avatar_v2.py`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/scripts/train_avatar_v2.py`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/scripts/evaluate_avatar_compass_v2.py`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/data/avatar_corpus_v2/corpus.jsonl`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/outputs/mlx_lora_avatar_v2_clean_best/`
- `/Users/lingjue/Documents/shutong/04-工作区/书童7B训练/outputs/evaluation_reports/compass_report_clean_boundary_v2_20260717_222419.json`
