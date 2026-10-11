-- BigQuery Graph over a compact, idempotent whole-outfit projection.
CREATE SCHEMA IF NOT EXISTS `data-workshops.flairify` OPTIONS(location='us-central1');
CREATE TABLE IF NOT EXISTS `data-workshops.flairify.graph_looks` (
 owner STRING NOT NULL, id STRING NOT NULL, wardrobe_version STRING, occasion STRING,
 complete BOOL, score FLOAT64, assessment_source STRING, model_version STRING, assessed_at TIMESTAMP,
 garment_ids ARRAY<STRING>, product_ids ARRAY<STRING>,
 PRIMARY KEY(owner,id) NOT ENFORCED
) CLUSTER BY owner, wardrobe_version;
CREATE OR REPLACE VIEW `data-workshops.flairify.graph_v_customers` AS
 SELECT DISTINCT owner,owner id FROM `data-workshops.flairify.graph_looks`;
CREATE OR REPLACE VIEW `data-workshops.flairify.graph_v_garments` AS
 SELECT DISTINCT owner,id FROM `data-workshops.flairify.graph_looks`,UNNEST(garment_ids) id;
CREATE OR REPLACE VIEW `data-workshops.flairify.graph_v_products` AS
 SELECT DISTINCT owner,id FROM `data-workshops.flairify.graph_looks`,UNNEST(product_ids) id;
CREATE OR REPLACE VIEW `data-workshops.flairify.graph_v_owns` AS
 SELECT DISTINCT owner,owner customer_id,id garment_id FROM `data-workshops.flairify.graph_v_garments`;
CREATE OR REPLACE VIEW `data-workshops.flairify.graph_v_wears` AS
 SELECT owner,id outfit_id,garment_id FROM `data-workshops.flairify.graph_looks`,UNNEST(garment_ids) garment_id;
CREATE OR REPLACE VIEW `data-workshops.flairify.graph_v_adds` AS
 SELECT owner,id outfit_id,product_id FROM `data-workshops.flairify.graph_looks`,UNNEST(product_ids) product_id;
CREATE OR REPLACE PROPERTY GRAPH `data-workshops.flairify.WardrobeGraph`
NODE TABLES (
 `data-workshops.flairify.graph_v_customers` AS Customers KEY(owner,id) LABEL Customer,
 `data-workshops.flairify.graph_v_garments` AS Garments KEY(owner,id) LABEL Garment,
 `data-workshops.flairify.graph_v_products` AS Products KEY(owner,id) LABEL Product,
 `data-workshops.flairify.graph_looks` AS Outfits KEY(owner,id) LABEL Outfit
 PROPERTIES(owner,id,wardrobe_version,occasion,complete,score,assessment_source,model_version,assessed_at)
)
EDGE TABLES (
 `data-workshops.flairify.graph_v_owns` AS Ownership KEY(owner,customer_id,garment_id)
 SOURCE KEY(owner,customer_id) REFERENCES Customers(owner,id)
 DESTINATION KEY(owner,garment_id) REFERENCES Garments(owner,id) LABEL Owns,
 `data-workshops.flairify.graph_v_wears` AS Worn KEY(owner,outfit_id,garment_id)
 SOURCE KEY(owner,outfit_id) REFERENCES Outfits(owner,id)
 DESTINATION KEY(owner,garment_id) REFERENCES Garments(owner,id) LABEL Wears,
 `data-workshops.flairify.graph_v_adds` AS Added KEY(owner,outfit_id,product_id)
 SOURCE KEY(owner,outfit_id) REFERENCES Outfits(owner,id)
 DESTINATION KEY(owner,product_id) REFERENCES Products(owner,id) LABEL Adds
);
