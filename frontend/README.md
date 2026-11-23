# Movie Recommend Frontend

This directory contains the static Vue-free frontend for the movie recommendation demo. It uses browser JavaScript and can run without a build step.

## Run

From the repository root:

```powershell
python -m http.server 8001 --directory frontend
```

Open `http://127.0.0.1:8001`. Set `API_BASE_URL` and `DATA_MODE` in `js/config.js` to use the FastAPI backend. `auto` probes the backend and falls back to the bundled mock service; `real` requires the backend; `mock` always uses local demo data.

## Backend Integration（已对齐 backend/app/api/api_contract.md）

- **认证**：登录返回并保存 `refresh_token`；access token（900 秒）过期后自动调用 `POST /api/auth/refresh` 续期并重试原请求；退出调用 `POST /api/auth/logout`；修改密码成功后强制重新登录（后端会使旧令牌失效）；支持邮箱验证码找回密码（request/confirm 两步）。
- **评分**：严格按后端 `RatingSubmit` 校验 —— 1-5 整数。所有评分入口（详情页评价条、打分页、快速连评、卡片快捷评分）都提供 **1~5 星一键档位按钮**（很差/较差/还行/推荐/力荐），也保留星级点选；提交后提示 `recommendation_refresh_queued` 状态。
- **分类**：分类胶囊与筛选弹层使用真实接口 `GET /api/movies/categories`（不再假设固定 ID）；详情页类型标签使用电影详情中的 `categories` 关联。
- **评论**：详情页热门影评对接 `GET /api/comments/movies/{id}/comments`、`POST /api/comments`、`POST /api/comments/{id}/like`、`DELETE /api/comments/{id}`、`POST /api/comments/{id}/reports`（含举报原因选择）。
- **推荐**：生成接口返回 202 + `task_id`，前端在 Spark 三步动效中轮询 `GET /api/recommend/task/{task_id}` 直到 SUCCESS/FAILURE，再读取 `GET /api/recommend/result`；列表项展示 `recommendation_source`（ALS 个性化/热门补位/历史推荐）与 0-1 `prediction_score`（本列表排序分，不是概率或电影评分）；曝光/点击/不感兴趣通过 `POST /api/recommend/event` 上报。
- **相似电影**：详情页“喜欢这部电影的人也喜欢”对接 `GET /api/recommend/similar/{movieid}`。
- **管理员**：管理后台页（页脚「🛠 管理后台」入口）对接 `POST /api/admin/login`、`GET /api/admin/me`、`POST /api/admin/logout`、`POST /api/admin/register`（`X-Admin-Bootstrap-Token` 首次初始化），电影管理写接口 `POST/PUT/DELETE /api/movies` 与分类接口。
- **反馈**：搜索无结果时可向管理员反馈缺失影片 —— `POST /api/feedback`（用户）、`GET /api/feedback/me`（用户）、`GET /api/feedback/admin/list`（管理员）、`PUT /api/feedback/admin/{id}`（管理员处理）。数据库表 `moviefeedback` 由 `backend/migrations/0006_moviefeedback.sql` 创建。

## Pages

- 首页精选 / 全部影片（排序+分页）/ 搜索（中文名自动翻译英文片名）
- 个性打分（1-5 星一键档位）、猜你喜欢（任务轮询 + 结果缓存）
- 电影详情（评分/收藏/评论/快速连评/相似影片）
- 热门影评：**电影下拉切换**，可查看任意电影评论区（分页、点赞/删除/举报），一键跳转详情页
- 我的评分 / 我的收藏 / **我的评论**（分页查看、删除自己的评论）

## Admin Setup

1. 后端 `.env` 配置 `ADMIN_BOOTSTRAP_TOKEN`。
2. 前端页脚点「管理后台」→ 首次使用表单粘贴 Bootstrap Token 并创建管理员账号。
3. 用该账号登录后台，即可上传电影（含分类多选）并处理用户反馈。

## UI Notes

- 详情页顺序：核心信息 → 我的评分与推荐定制 → **剧情简介 → 热门影评** → 快速连评 → 相似影片。
- 登录卡片左侧仅保留「专属私人影院」标题与算法徽章。

## Recommendation Display

The recommendation page displays up to 20 results, ordered by `position`. Each result includes its movie details, source (`als_rerank`, `popular_fallback`, or `legacy`) and, for current batches, a 0-1 list ranking score. The score is not a movie rating, probability, or cross-list quality measure.

The backend trains ALS offline and publishes candidate JSONL. Celery reads those candidates to refresh a user's result after rating submission, combines their offline order with current rating genre preferences and a popularity list, and writes the result to MySQL and Redis. This refresh does not train ALS in the request path. See [recommendation-worker.md](../docs/recommendation-worker.md) and [api_contract.md](../backend/app/api/api_contract.md) for the current contracts.

## Verification

Run the frontend mock smoke test from the repository root:

```powershell
node frontend/tests/smoke_test.js
```

The smoke test covers mock authentication (including refresh/forgot-password), 1-5 ratings, favorites, comments (post/like/report/delete), categories, recommendation task/result shape and 0-1 scores, feedback, my comments, admin bootstrap/login/movie-create and feedback handling, and movie APIs. It does not connect to MySQL, Redis, Celery, or Spark.
