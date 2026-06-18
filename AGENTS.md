# AGENTS.md

本檔案是 OpenAI Codex 在此專案的入口規則。開始工作前必須讀完。

## 讀取順序

1. 先讀 `docs/PROJECT_RULES.md`
2. 再讀 `docs/STATUS.md`
3. 依 `current_action` 執行 `docs/PROJECT_RULES.md` 對應標題章節
4. 若 `current_action` 為 `executing`，依 `current_task` 指定的 task-id，讀取對應的 `{task-id}-spec.md`、`{task-id}-plan.md`、最新 log

## 與 Claude Code 的協作方式

- 預設由 Codex 協助使用者釐清需求，再整理可交付給 Claude Code 的執行提示詞
- Codex 的預設責任是提示詞設計與成果檢查，不作為主要實作者
- Claude Code 完成後，檢查文件、程式碼與驗證結果，指出需要補充或修改之處
- 只有在使用者明確要求時，Codex 才直接修改文件或程式碼
- 提示詞至少要說明：目標、範圍、預期產出、驗證方式，以及是否允許更新 task 文件
- 任務涉及大型程式碼庫探索、AST 查詢或自動化重構時，提示詞可要求 Claude Code 評估是否需要 Tree-sitter；不要預設要求安裝
- 提示詞不能取代 `docs/STATUS.md`、已確認的 spec、plan 與最新 log
- 需要跨 session 保留的資訊，寫入 spec、plan、log 或 `docs/STATUS.md`，不要只留在提示詞內

## 編碼判斷規則

- 不得因為終端顯示亂碼，就直接判定檔案編碼錯誤
- 先讀 raw bytes，檢查是否有 UTF-8 BOM
- 再用 `[System.Text.Encoding]::UTF8.GetString(...)` 明確解碼
- 換行用位元組判斷：`0D 0A` 視為 CRLF，`0A` 視為 LF
- 只有在 bytes、BOM、解碼結果彼此矛盾時，才懷疑檔案真的有編碼問題
