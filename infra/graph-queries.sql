-- Graph fallback: all queries bind @owner from the verified identity, never client user IDs.
-- Distinct, assessed whole-outfit coverage for each jacket.
-- Prices and live stock must still be read from Firestore, not this projection.
SELECT target_id AS product_id, COUNT(DISTINCT outfit_id) AS distinct_assessed_outfits,
       AVG(score) AS mean_score, ARRAY_AGG(DISTINCT reason LIMIT 5) AS reasons
FROM `data-workshops.flairify.relationships`
WHERE owner=@owner AND relationship='OUTFIT_CONTAINS_PRODUCT'
  AND score >= 0.7 AND occasion=@occasion
GROUP BY product_id
ORDER BY distinct_assessed_outfits DESC, mean_score DESC
LIMIT 20;

-- Two-hop candidate complement paths do not prove complete outfit compatibility.
SELECT own.source_id AS user_id, own.target_id AS garment_id, candidate.target_id AS product_id,
       candidate.score, candidate.reason, candidate.model_version, candidate.assessed_at
FROM `data-workshops.flairify.relationships` own
JOIN `data-workshops.flairify.relationships` candidate
 ON own.owner=candidate.owner AND own.target_id=candidate.source_id
WHERE own.owner=@owner AND own.relationship='OWNS'
 AND candidate.relationship='CANDIDATE_COMPLEMENT'
ORDER BY candidate.score DESC LIMIT 60;

-- User data removal, run before deleting a local projection outbox item.
DELETE FROM `data-workshops.flairify.relationships` WHERE owner=@owner;
DELETE FROM `data-workshops.flairify.nodes` WHERE owner=@owner;
