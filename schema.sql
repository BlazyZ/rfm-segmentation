CREATE TABLE IF NOT EXISTS analysis_batches (
 id CHAR(32) CHARACTER SET ascii PRIMARY KEY,
 filename VARCHAR(255) NOT NULL,
 source_path TEXT NOT NULL,
 source_sha CHAR(64) CHARACTER SET ascii NOT NULL,
 window_start DATE NOT NULL,
 window_end DATE NOT NULL,
 reference_date DATE NOT NULL,
 rules_version VARCHAR(32) NOT NULL DEFAULT 'rfm-v1',
 status VARCHAR(16) NOT NULL,
 progress VARCHAR(500) NOT NULL DEFAULT '',
 error TEXT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 completed_at DATETIME NULL,
 duration_seconds DECIMAL(12,3) NULL,
 summary JSON NULL,
 INDEX idx_signature(source_sha, window_start, window_end, reference_date, rules_version, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS transaction_lines (
 batch_id CHAR(32) CHARACTER SET ascii NOT NULL,
 source_row BIGINT NOT NULL,
 kh VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 dtime DATETIME(6) NOT NULL,
 syjh VARCHAR(100) NOT NULL,
 djh VARCHAR(4) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 spbm TEXT NOT NULL,
 spmc TEXT NOT NULL,
 sl VARCHAR(100) NOT NULL,
 sj VARCHAR(100) NOT NULL,
 je VARCHAR(100) NOT NULL,
 jf VARCHAR(100) NOT NULL,
 gzbm TEXT NOT NULL,
 gzmc TEXT NOT NULL,
 amount_cents BIGINT NOT NULL,
 PRIMARY KEY(batch_id, source_row),
 INDEX idx_customer_time(batch_id, kh, dtime),
 FOREIGN KEY(batch_id) REFERENCES analysis_batches(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS customer_rfm (
 batch_id CHAR(32) CHARACTER SET ascii NOT NULL,
 kh VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 last_purchase DATETIME(6) NOT NULL,
 r INT NOT NULL,
 f INT NOT NULL,
 m_cents BIGINT NOT NULL,
 detail_count INT NOT NULL,
 r_score TINYINT NOT NULL,
 f_score TINYINT NOT NULL,
 m_score TINYINT NOT NULL,
 segment_code CHAR(3) CHARACTER SET ascii NOT NULL,
 segment VARCHAR(32) NOT NULL,
 PRIMARY KEY(batch_id, kh),
 INDEX idx_segment_amount(batch_id, segment_code, m_cents),
 FOREIGN KEY(batch_id) REFERENCES analysis_batches(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS app_state (
 id TINYINT PRIMARY KEY,
 active_batch_id CHAR(32) CHARACTER SET ascii NULL,
 FOREIGN KEY(active_batch_id) REFERENCES analysis_batches(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT IGNORE INTO app_state(id, active_batch_id) VALUES(1, NULL);
