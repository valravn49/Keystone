-- schema.sql

-- Table of sisters (personality + DOB pulled from config.json)
CREATE TABLE IF NOT EXISTS sisters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    dob DATE NOT NULL,
    personality TEXT,
    cooldown_msgs_per_hour INTEGER DEFAULT 3,
    llm_style TEXT
);

-- Table to log daily rotation
CREATE TABLE IF NOT EXISTS rotation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    lead_sister TEXT NOT NULL,
    rest_sister TEXT NOT NULL,
    support_sisters TEXT NOT NULL,
    theme TEXT NOT NULL,
    wake_time TEXT,
    plug_status TEXT,
    partner_service_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store themes (rotates weekly)
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- Table to track hygiene confirmations
CREATE TABLE IF NOT EXISTS hygiene_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    confirmed BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to track partner service tasks
CREATE TABLE IF NOT EXISTS partner_service (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week TEXT NOT NULL,
    arranged BOOLEAN DEFAULT 0,
    completed BOOLEAN DEFAULT 0,
    same_day_modifier BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
