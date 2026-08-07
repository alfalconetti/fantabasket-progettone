-- Tabella statistiche basketball-reference (append giornaliero)
CREATE TABLE IF NOT EXISTS bref_stats (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stagione    VARCHAR(10) NOT NULL,
    nome_bref   TEXT NOT NULL,
    team        TEXT,
    g           INT,
    mp          NUMERIC(5,1),
    fgm         NUMERIC(5,1),
    fga         NUMERIC(5,1),
    fg_pct      NUMERIC(5,3),
    fg3m        NUMERIC(5,1),
    fg3a        NUMERIC(5,1),
    fg3_pct     NUMERIC(5,3),
    ftm         NUMERIC(5,1),
    fta         NUMERIC(5,1),
    ft_pct      NUMERIC(5,3),
    orb         NUMERIC(5,1),
    drb         NUMERIC(5,1),
    trb         NUMERIC(5,1),
    ast         NUMERIC(5,1),
    stl         NUMERIC(5,1),
    blk         NUMERIC(5,1),
    tov         NUMERIC(5,1),
    pf          NUMERIC(5,1),
    pts         NUMERIC(5,1),
    fantamedia  NUMERIC(6,2) GENERATED ALWAYS AS (
        fga*(-0.5) + fgm*1 + ftm*1 + fta*(-0.75) + fg3m*1.5 +
        pts*0.5 + orb*2 + drb*1.25 + ast*2 + stl*2 + blk*2 + tov*(-2)
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_bref_stats_stagione_nome
    ON bref_stats (stagione, nome_bref);
CREATE INDEX IF NOT EXISTS idx_bref_stats_timestamp
    ON bref_stats (timestamp);
