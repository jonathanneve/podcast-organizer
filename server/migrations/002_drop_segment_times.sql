ALTER TABLE episode_segments DROP COLUMN start_time;
ALTER TABLE episode_segments DROP COLUMN end_time;
ALTER TABLE episode_segments ADD COLUMN segment_order INTEGER NOT NULL DEFAULT 0;
