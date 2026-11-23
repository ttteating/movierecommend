-- 用户反馈表:搜不到电影时向管理员提交,管理员核实后上传电影并处理反馈
-- 在任何数据库执行前请先备份。
CREATE TABLE IF NOT EXISTS `moviefeedback` (
  `feedbackid` bigint NOT NULL AUTO_INCREMENT,
  `userid` int NOT NULL,
  `moviename` varchar(500) NOT NULL COMMENT '用户反馈缺失的电影名/关键词',
  `note` varchar(1000) NULL DEFAULT NULL COMMENT '补充说明:年份/导演/主演等',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT 'pending=待处理 resolved=已处理',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `resolved_at` datetime(6) NULL DEFAULT NULL,
  PRIMARY KEY (`feedbackid`) USING BTREE,
  KEY `idx_moviefeedback_status_created` (`status`, `created_at`) USING BTREE,
  KEY `idx_moviefeedback_user_created` (`userid`, `created_at`) USING BTREE,
  CONSTRAINT `fk_moviefeedback_user` FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = DYNAMIC;
