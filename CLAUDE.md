# CLAUDE.md

本檔案是 Claude Code 在此專案的入口規則。開始工作前必須讀完。

## 讀取順序

1. 先讀 `docs/PROJECT_RULES.md`
2. 再讀 `docs/STATUS.md`
3. 依 `current_action` 執行 `docs/PROJECT_RULES.md` 對應標題章節
4. 若 `current_action` 為 `executing`，依 `current_task` 指定的 task-id，讀取對應的 `{task-id}-spec.md`、`{task-id}-plan.md`、最新 log

## 接收 Codex 提示詞時

- Codex 提供的提示詞是本次工作的執行簡報，不取代 `docs/STATUS.md`、已確認的 spec、plan 與最新 log
- 收到提示詞後，仍必須先依讀取順序確認共享狀態與當前 task 文件
- 若提示詞與已確認的 task 文件衝突，先停止執行並請使用者確認
- 需要跨 session 保留的資訊，寫入 spec、plan、log 或 `docs/STATUS.md`
- 完成後回報變更範圍、驗證結果與仍待確認事項，供 Codex 或使用者檢查
- 若提示詞要求評估 Tree-sitter，先說明用途、成本、替代方案與預期收益；未經使用者確認不得安裝 bindings 或語言 grammar
