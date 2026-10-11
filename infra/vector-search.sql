-- Uses exact distance for a bounded catalogue; no vector index or reservation required.
-- @embedding is ARRAY<FLOAT64>, @owner is the trusted retailer namespace.
SELECT id, ML.DISTANCE(embedding,@embedding,'COSINE') AS distance
FROM `data-workshops.flairify.products`
WHERE owner=@owner AND ARRAY_LENGTH(embedding)=ARRAY_LENGTH(@embedding)
 AND ARRAY_LENGTH(embedding)>0
ORDER BY distance LIMIT 30;
-- Configure maximum_bytes_billed on every submitted query.
