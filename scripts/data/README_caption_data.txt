Caption data for TikTok automation

Files:
1) caption_master.csv
   - Editable source (open with Excel)
   - Encoding: UTF-8 (BOM)
2) caption_bank.json
   - Auto-generated runtime bank
3) ..\state\caption_history.json
   - Auto-generated anti-repeat history

CSV columns:
- product_code: product key in video name (BCR, MKRC, ...)
- product_name: optional display name
- caption: main text
- hashtags: separated by "|" (example: #a|#b|#c)
- weight: integer 1..100 (higher = more likely)
- active: 1 enabled, 0 disabled

Typical flow:
1) Edit caption_master.csv
2) Run:
   python D:\MUMU\scripts\caption_bank_tool.py build
3) Validate quality (recommended before schedule):
   python D:\MUMU\scripts\caption_bank_tool.py validate --fail-on-warning
4) Pick by video filename:
   python D:\MUMU\scripts\caption_bank_tool.py pick --video "250807-BCR-upload.mp4"

Reliability features in `pick`:
- Auto rebuilds caption_bank.json if CSV is newer.
- Validates CSV before picking (can disable with --no-validate-before-pick).
- Supports strict code mode: --strict-code
- Caps final caption text length: --max-chars 1600
