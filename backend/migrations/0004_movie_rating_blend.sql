-- Run once against the selected database after taking a backup.
-- Existing movieinfo values are retained as the crawler baseline.
ALTER TABLE `movieinfo`
  ADD COLUMN `web_averating` double NULL,
  ADD COLUMN `web_numrating` int NULL,
  ADD COLUMN `site_averating` double NULL,
  ADD KEY `idx_movieinfo_web_numrating` (`web_numrating`);

UPDATE `movieinfo`
SET `web_averating` = `averating`,
    `web_numrating` = `numrating`;

UPDATE `movieinfo` AS m
LEFT JOIN (
  SELECT `movieid`, CAST(AVG(`rating`) AS DOUBLE) AS `site_average`,
    COUNT(*) AS `site_count`
  FROM `personalratings`
  GROUP BY `movieid`
) AS r ON r.`movieid` = m.`movieid`
SET m.`site_averating` = r.`site_average`,
    m.`numrating` = COALESCE(r.`site_count`, 0),
    m.`averating` = CASE
      WHEN COALESCE(r.`site_count`, 0) = 0 THEN m.`web_averating`
      WHEN m.`web_averating` IS NULL THEN ROUND(r.`site_average`, 1)
      ELSE ROUND(
        (m.`web_averating` * 20 + r.`site_average` * r.`site_count`)
        / (20 + r.`site_count`),
        1
      )
    END;
