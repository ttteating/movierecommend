-- MySQL 8.0. All results are violation counts and must be zero.
-- Physical NOT NULL / PK / UNIQUE / FK / CHECK checks are also generated
-- from the latest dump by generate_mock_data.py before COMMIT.

-- No logical orphans in the legacy table (it has no physical FK).
SELECT COUNT(*) FROM recommendresult r
LEFT JOIN `user` u ON u.userid=r.userid
LEFT JOIN movieinfo m ON m.movieid=r.movieid
WHERE r.userid IS NULL OR r.movieid IS NULL OR u.userid IS NULL OR m.movieid IS NULL;

-- Legacy pairs deliberately kept unique by this generator, although not constrained by DDL.
SELECT COUNT(*) FROM (
  SELECT userid,movieid FROM recommendresult GROUP BY userid,movieid HAVING COUNT(*)>1
) duplicates;

-- Same request must have one user/time, unique positive contiguous positions.
SELECT COUNT(*) FROM (
  SELECT request_id FROM recommendationitem GROUP BY request_id
  HAVING COUNT(DISTINCT userid)<>1 OR COUNT(DISTINCT generated_at)<>1
     OR MIN(position)<>1 OR MAX(position)<>COUNT(*) OR COUNT(DISTINCT position)<>COUNT(*)
) bad_requests;

-- Event time cannot precede generation; feedback requires an earlier exposure.
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

-- Current state equals the final like/unlike operation (ties broken by event ID).
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

-- An event also needs a current relationship row.
SELECT COUNT(*) FROM commentlike_event e LEFT JOIN commentlike l
ON l.userid=e.userid AND l.commentid=e.commentid WHERE l.id IS NULL;

-- Transitions start at like, alternate, and occur strictly in time order.
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

-- Generator mirror policy: legacy row matches an item in that user's final simulated request.
-- Scope this policy to generator usernames; it is not a schema constraint for other data.
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
