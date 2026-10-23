-- MySQL 8.0: all 56 SELECT results must be zero. Includes physical and business constraints.

SELECT COUNT(*) FROM `user` WHERE `userid` IS NULL OR `username` IS NULL OR `password` IS NULL OR `phone` IS NULL OR `email` IS NULL OR `status` IS NULL OR `created_at` IS NULL OR `updated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `userid` FROM `user` WHERE `userid` IS NOT NULL GROUP BY `userid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `active_email` FROM `user` WHERE `active_email` IS NOT NULL GROUP BY `active_email` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `active_phone` FROM `user` WHERE `active_phone` IS NOT NULL GROUP BY `active_phone` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `active_username` FROM `user` WHERE `active_username` IS NOT NULL GROUP BY `active_username` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `personalratings` WHERE `ratingid` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `rating` IS NULL OR `rated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `ratingid` FROM `personalratings` WHERE `ratingid` IS NOT NULL GROUP BY `ratingid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `userid`,`movieid` FROM `personalratings` WHERE `userid` IS NOT NULL AND `movieid` IS NOT NULL GROUP BY `userid`,`movieid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `personalratings` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `personalratings` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `personalratings` WHERE NOT ((`rating` between 1 and 10));

SELECT COUNT(*) FROM `userfavorite` WHERE `id` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `status` IS NULL OR `created_at` IS NULL OR `updated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `id` FROM `userfavorite` WHERE `id` IS NOT NULL GROUP BY `id` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `userid`,`movieid` FROM `userfavorite` WHERE `userid` IS NOT NULL AND `movieid` IS NOT NULL GROUP BY `userid`,`movieid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `userfavorite` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `userfavorite` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `userfavorite` WHERE NOT ((`status` in (_utf8mb4'want_to_watch',_utf8mb4'watched')));

SELECT COUNT(*) FROM `moviecomment` WHERE `commentid` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `content` IS NULL OR `moderation_status` IS NULL OR `created_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `commentid` FROM `moviecomment` WHERE `commentid` IS NOT NULL GROUP BY `commentid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `moviecomment` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `moviecomment` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `moviecomment` WHERE NOT ((`moderation_status` in (_utf8mb4'published',_utf8mb4'review_pending',_utf8mb4'hidden')));

SELECT COUNT(*) FROM `commentlike` WHERE `id` IS NULL OR `userid` IS NULL OR `commentid` IS NULL OR `is_active` IS NULL OR `created_at` IS NULL OR `updated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `id` FROM `commentlike` WHERE `id` IS NOT NULL GROUP BY `id` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `userid`,`commentid` FROM `commentlike` WHERE `userid` IS NOT NULL AND `commentid` IS NOT NULL GROUP BY `userid`,`commentid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `commentlike` c LEFT JOIN `moviecomment` p ON c.`commentid`=p.`commentid` WHERE c.`commentid` IS NOT NULL AND p.`commentid` IS NULL;

SELECT COUNT(*) FROM `commentlike` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `commentlike_event` WHERE `eventid` IS NULL OR `userid` IS NULL OR `commentid` IS NULL OR `action` IS NULL OR `created_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `eventid` FROM `commentlike_event` WHERE `eventid` IS NOT NULL GROUP BY `eventid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `commentlike_event` c LEFT JOIN `moviecomment` p ON c.`commentid`=p.`commentid` WHERE c.`commentid` IS NOT NULL AND p.`commentid` IS NULL;

SELECT COUNT(*) FROM `commentlike_event` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `commentlike_event` WHERE NOT ((`action` in (_utf8mb4'like',_utf8mb4'unlike')));

SELECT COUNT(*) FROM `recommendationitem` WHERE `recommendationid` IS NULL OR `request_id` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `position` IS NULL OR `generated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `recommendationid` FROM `recommendationitem` WHERE `recommendationid` IS NOT NULL GROUP BY `recommendationid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `request_id`,`movieid` FROM `recommendationitem` WHERE `request_id` IS NOT NULL AND `movieid` IS NOT NULL GROUP BY `request_id`,`movieid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `recommendationitem` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `recommendationitem` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `recommendationevent` WHERE `eventid` IS NULL OR `recommendationid` IS NULL OR `event_type` IS NULL OR `created_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `eventid` FROM `recommendationevent` WHERE `eventid` IS NOT NULL GROUP BY `eventid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `recommendationevent` c LEFT JOIN `recommendationitem` p ON c.`recommendationid`=p.`recommendationid` WHERE c.`recommendationid` IS NOT NULL AND p.`recommendationid` IS NULL;

SELECT COUNT(*) FROM `recommendationevent` WHERE NOT ((`event_type` in (_utf8mb4'impression',_utf8mb4'click',_utf8mb4'not_interested')));






SELECT COUNT(*) FROM recommendresult r
LEFT JOIN `user` u ON u.userid=r.userid
LEFT JOIN movieinfo m ON m.movieid=r.movieid
WHERE r.userid IS NULL OR r.movieid IS NULL OR u.userid IS NULL OR m.movieid IS NULL;




SELECT COUNT(*) FROM (
  SELECT userid,movieid FROM recommendresult GROUP BY userid,movieid HAVING COUNT(*)>1
) duplicates;




SELECT COUNT(*) FROM (
  SELECT request_id FROM recommendationitem GROUP BY request_id
  HAVING COUNT(DISTINCT userid)<>1 OR COUNT(DISTINCT generated_at)<>1
     OR MIN(position)<>1 OR MAX(position)<>COUNT(*) OR COUNT(DISTINCT position)<>COUNT(*)
) bad_requests;




WITH first_impression AS (
 SELECT recommendationid,MIN(created_at) exposed_at FROM recommendationevent
 WHERE event_type='impression' GROUP BY recommendationid
)
SELECT COUNT(*) FROM recommendationevent e
JOIN recommendationitem i ON i.recommendationid=e.recommendationid
LEFT JOIN first_impression p ON p.recommendationid=e.recommendationid
WHERE e.created_at<i.generated_at OR
 (e.event_type IN ('click','not_interested') AND
  (p.recommendationid IS NULL OR p.exposed_at>e.created_at));




WITH ranked AS (
 SELECT e.*,ROW_NUMBER() OVER (
   PARTITION BY userid,commentid ORDER BY created_at DESC,eventid DESC
 ) rn FROM commentlike_event e
)
SELECT COUNT(*) FROM commentlike l LEFT JOIN ranked e
ON e.userid=l.userid AND e.commentid=l.commentid AND e.rn=1
WHERE e.eventid IS NULL OR l.is_active NOT IN (0,1)
 OR l.is_active<>(e.action='like') OR l.updated_at<>e.created_at
 OR l.created_at>l.updated_at;




SELECT COUNT(*) FROM commentlike_event e LEFT JOIN commentlike l
ON l.userid=e.userid AND l.commentid=e.commentid WHERE l.id IS NULL;




WITH history AS (
 SELECT e.*,LAG(action) OVER (
   PARTITION BY userid,commentid ORDER BY created_at,eventid
 ) previous_action,LAG(created_at) OVER (
   PARTITION BY userid,commentid ORDER BY created_at,eventid
 ) previous_time FROM commentlike_event e
)
SELECT COUNT(*) FROM history WHERE (previous_action IS NULL AND action<>'like')
 OR previous_action=action OR previous_time>=created_at;



WITH first_like AS (
 SELECT userid,commentid,MIN(created_at) first_at
 FROM commentlike_event GROUP BY userid,commentid
)
SELECT COUNT(*) FROM commentlike l JOIN first_like e
 ON e.userid=l.userid AND e.commentid=l.commentid
 WHERE l.created_at<>e.first_at;



SELECT COUNT(*) FROM commentlike_event e
JOIN moviecomment c ON c.commentid=e.commentid JOIN `user` u ON u.userid=e.userid
WHERE e.created_at<c.created_at OR e.created_at<u.created_at;



SELECT COUNT(*) FROM personalratings r JOIN `user` u ON u.userid=r.userid
WHERE r.rated_at<u.created_at OR (r.timestamp IS NOT NULL AND
 (r.timestamp NOT REGEXP '^[0-9]{1,10}$' OR
  CAST(r.timestamp AS UNSIGNED)<>TIMESTAMPDIFF(SECOND,'1970-01-01 00:00:00',r.rated_at)));



SELECT COUNT(*) FROM moviecomment c JOIN `user` u ON u.userid=c.userid
WHERE c.created_at<u.created_at OR c.deleted_at<c.created_at;



SELECT COUNT(*) FROM userfavorite f JOIN `user` u ON u.userid=f.userid
WHERE f.created_at<u.created_at OR f.updated_at<f.created_at
 OR f.deleted_at<f.created_at OR f.deleted_at>f.updated_at;



SELECT COUNT(*) FROM recommendationitem i JOIN `user` u ON u.userid=i.userid
WHERE i.generated_at<u.created_at;



SELECT COUNT(*) FROM `user` WHERE created_at>updated_at
 OR deleted_at<created_at OR deleted_at>updated_at;





WITH latest_request AS (
 SELECT i.userid,MAX(i.request_id) request_id
 FROM recommendationitem i JOIN `user` u ON u.userid=i.userid
 WHERE u.username REGEXP '^sim[0-9a-f]{1,12}_[0-9]{6}$'
 GROUP BY i.userid
)
SELECT COUNT(*) FROM recommendresult r JOIN `user` u ON u.userid=r.userid
LEFT JOIN latest_request lr ON lr.userid=r.userid
LEFT JOIN recommendationitem i FORCE INDEX (uk_recommendationitem_request_movie)
 ON i.request_id=lr.request_id AND i.movieid=r.movieid
LEFT JOIN movieinfo m ON m.movieid=i.movieid
WHERE u.username REGEXP '^sim[0-9a-f]{1,12}_[0-9]{6}$' AND
 (i.recommendationid IS NULL OR NOT (r.moviename<=>m.moviename)
  OR NOT (r.rating IS NULL AND i.movie_rating_snapshot IS NULL
      OR r.rating IS NOT NULL AND i.movie_rating_snapshot IS NOT NULL
         AND ABS(r.rating-i.movie_rating_snapshot)<0.0001));
