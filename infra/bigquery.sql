-- Standard SQL fallback. Run with location us-central1. No reserved slots required.
CREATE SCHEMA IF NOT EXISTS `data-workshops.flairify` OPTIONS(location='us-central1');
CREATE TABLE IF NOT EXISTS `data-workshops.flairify.products` (
 owner STRING NOT NULL, id STRING NOT NULL, description STRING, embedding ARRAY<FLOAT64>, content_hash STRING,
 PRIMARY KEY(owner,id) NOT ENFORCED
) CLUSTER BY owner, id;
CREATE TABLE IF NOT EXISTS `data-workshops.flairify.nodes` (
 owner STRING NOT NULL, id STRING NOT NULL, kind STRING NOT NULL, label STRING,
 PRIMARY KEY(owner,id) NOT ENFORCED
) CLUSTER BY owner, kind;
CREATE TABLE IF NOT EXISTS `data-workshops.flairify.relationships` (
 owner STRING NOT NULL, id STRING NOT NULL, source_id STRING NOT NULL, target_id STRING NOT NULL,
 relationship STRING NOT NULL, outfit_id STRING, score FLOAT64, reason STRING, assessment_source STRING,
 model_version STRING, assessed_at TIMESTAMP, occasion STRING, feedback STRING,
 PRIMARY KEY(owner,id) NOT ENFORCED
) CLUSTER BY owner, relationship;
CREATE TABLE IF NOT EXISTS `data-workshops.flairify.evaluation` (
 run_id STRING, method STRING, scenario STRING, outfit_id STRING, total_inr INT64,
 budget_valid BOOL, stock_valid BOOL, owned_valid BOOL, complete BOOL, elapsed_ms FLOAT64,
 human_relevance INT64, human_explanation INT64, collected_at TIMESTAMP
) PARTITION BY DATE(collected_at);
