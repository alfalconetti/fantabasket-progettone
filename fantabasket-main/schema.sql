-- ============================================================
-- FANTABASKET MAIN DB — Schema PostgreSQL
-- ============================================================

CREATE TABLE giocatori (
    id              SERIAL PRIMARY KEY,
    nome_bref       TEXT NOT NULL,
    nome_yahoo      TEXT,
    nome_common     TEXT NOT NULL,
    nome_norm       TEXT NOT NULL,
    data_nascita    DATE
);

CREATE INDEX idx_giocatori_nome_norm ON giocatori (nome_norm);
CREATE INDEX idx_giocatori_nome_bref ON giocatori (nome_bref);


CREATE TABLE contratti (
    id              SERIAL PRIMARY KEY,
    giocatore_id    INT NOT NULL REFERENCES giocatori(id),
    team_id         TEXT NOT NULL,
    importo         INT NOT NULL,
    anni_originali  INT NOT NULL,
    stagione_firma  TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN ('normale', 'rookie', '10day')),
    attivo          BOOLEAN NOT NULL DEFAULT TRUE,
    scadenza_10day  TIMESTAMPTZ
);

CREATE INDEX idx_contratti_team     ON contratti (team_id)       WHERE attivo = TRUE;
CREATE INDEX idx_contratti_giocatore ON contratti (giocatore_id) WHERE attivo = TRUE;


CREATE TABLE trade (
    id          SERIAL PRIMARY KEY,
    trade_ref   TEXT UNIQUE,                    -- es. TRADE-2025-001, NULL finché bozza
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    aggiornato  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stagione    TEXT NOT NULL,
    stato       TEXT NOT NULL DEFAULT 'bozza'
        CHECK (stato IN (
            'bozza',            -- in costruzione dal GM
            'proposta',         -- proposta agli altri GM, in attesa voti
            'in_approvazione',  -- tutti i GM hanno accettato, attende admin
            'approvata',        -- admin ha approvato, eseguita
            'rifiutata_gm',     -- almeno un GM ha rifiutato
            'rifiutata_admin',  -- admin ha rifiutato
            'annullata'         -- annullata dal proponente
        )),
    n_squadre   INT NOT NULL CHECK (n_squadre BETWEEN 2 AND 4),
    proposta_da TEXT NOT NULL,                  -- team_id del proponente
    bozza_num   INT,                            -- es. 3 = "Bozza #3 di Luca"; NULL dopo ufficializzazione
    note        TEXT,
    -- snapshot validazione al momento della proposta
    validazione_ok      BOOLEAN,
    validazione_note    TEXT,
    -- approvazione admin
    approvata_da        TEXT,                   -- team_id o nome admin
    approvata_at        TIMESTAMPTZ
);

-- bozza_num univoco per team tra le bozze attive
CREATE UNIQUE INDEX idx_trade_bozza_num ON trade (proposta_da, bozza_num)
    WHERE stato = 'bozza';

CREATE INDEX idx_trade_stato    ON trade (stato);
CREATE INDEX idx_trade_stagione ON trade (stagione);


CREATE TABLE trade_squadre (
    id          SERIAL PRIMARY KEY,
    trade_id    INT NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
    team_id     TEXT NOT NULL,
    ordine      INT NOT NULL,                   -- 1..N, ordine di inserimento
    confermata  BOOLEAN NOT NULL DEFAULT FALSE  -- il GM ha confermato i suoi asset
);

CREATE UNIQUE INDEX idx_trade_squadre_uq ON trade_squadre (trade_id, team_id);


CREATE TABLE trade_items (
    id              SERIAL PRIMARY KEY,
    trade_id        INT NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('giocatore', 'pick', 'diritti')),
    giocatore_id    INT REFERENCES giocatori(id),
    pick_id         INT,                        -- FK su pick.id
    team_id_da      TEXT NOT NULL,
    team_id_a       TEXT NOT NULL
);

CREATE INDEX idx_trade_items_trade ON trade_items (trade_id);


CREATE TABLE trade_voti (
    id          SERIAL PRIMARY KEY,
    trade_id    INT NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
    team_id     TEXT NOT NULL,
    voto        TEXT NOT NULL DEFAULT 'pending'
        CHECK (voto IN ('pending', 'accettato', 'rifiutato')),
    timestamp   TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_trade_voti_uq ON trade_voti (trade_id, team_id);


CREATE TABLE transazioni (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tipo            TEXT NOT NULL CHECK (tipo IN (
        'signed', 'traded', 'cut', 'renewed', 'expired',
        'decaduto', 'dpe_attivata',
        '10day_firma', '10day_scadenza',
        'rookie_firma', 'rookie_diritti_scaduti'
    )),
    giocatore_id    INT NOT NULL REFERENCES giocatori(id),
    team_id_da      TEXT,
    team_id_a       TEXT,
    stagione        TEXT NOT NULL,
    contratto_id    INT REFERENCES contratti(id),
    trade_id        INT REFERENCES trade(id),
    rookie_scale    BOOLEAN NOT NULL DEFAULT FALSE,
    gratuito        BOOLEAN NOT NULL DEFAULT FALSE,  -- taglio 1x1 gratuito (max 3/stagione)
    note            TEXT
);

CREATE INDEX idx_transazioni_giocatore ON transazioni (giocatore_id, timestamp DESC);
CREATE INDEX idx_transazioni_team_a    ON transazioni (team_id_a, stagione);
CREATE INDEX idx_transazioni_trade     ON transazioni (trade_id) WHERE trade_id IS NOT NULL;


CREATE TABLE pick (
    id                  SERIAL PRIMARY KEY,
    proprietario_orig   TEXT NOT NULL,
    proprietario_att    TEXT NOT NULL,
    anno                TEXT NOT NULL,
    round               INT NOT NULL CHECK (round IN (1, 2)),
    protezioni          JSONB,
    scattata            BOOLEAN NOT NULL DEFAULT FALSE,
    numero_scelta       INT
);

ALTER TABLE trade_items ADD CONSTRAINT fk_trade_items_pick
    FOREIGN KEY (pick_id) REFERENCES pick(id);

CREATE INDEX idx_pick_proprietario ON pick (proprietario_att) WHERE scattata = FALSE;


CREATE TABLE rookie (
    id                  SERIAL PRIMARY KEY,
    giocatore_id        INT NOT NULL REFERENCES giocatori(id),
    team_id             TEXT NOT NULL,
    round               INT NOT NULL CHECK (round IN (1, 2)),
    pick_numero         INT NOT NULL,
    anno_draft          TEXT NOT NULL,
    anno_firma          TEXT,
    anni_scala          INT NOT NULL DEFAULT 0,
    scadenza_diritti    TIMESTAMPTZ,
    firmato             BOOLEAN NOT NULL DEFAULT FALSE,
    diritti_scaduti     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_rookie_team ON rookie (team_id)
    WHERE firmato = FALSE AND diritti_scaduti = FALSE;


CREATE TABLE impatto_taglio (
    id              SERIAL PRIMARY KEY,
    team_id         TEXT NOT NULL,
    giocatore_id    INT NOT NULL REFERENCES giocatori(id),
    stagione_taglio TEXT NOT NULL,
    stagione        TEXT NOT NULL,
    importo         INT NOT NULL,
    transazione_id  INT REFERENCES transazioni(id)
);

CREATE INDEX idx_impatto_taglio_team ON impatto_taglio (team_id, stagione);


CREATE TABLE cambi_ruolo (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    giocatore_id    INT NOT NULL REFERENCES giocatori(id),
    team_id         TEXT NOT NULL,
    ruolo_da        TEXT,
    ruolo_a         TEXT NOT NULL,
    stagione        TEXT NOT NULL,
    tipo            TEXT NOT NULL CHECK (tipo IN (
        'iniziale', 'ordinario', 'erminio', 'saedro',
        'forzato_admin', 'post_trade', 'post_firma'
    )),
    scadenza        TIMESTAMPTZ,
    ruolo_ripristino TEXT
);

CREATE INDEX idx_cambi_ruolo_giocatore ON cambi_ruolo (giocatore_id, stagione, timestamp DESC);
CREATE INDEX idx_cambi_ruolo_scadenza  ON cambi_ruolo (scadenza) WHERE scadenza IS NOT NULL;


CREATE TABLE penalita (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    team_id         TEXT NOT NULL,
    stagione        TEXT NOT NULL,
    motivo          TEXT NOT NULL,
    assegnata_da    TEXT NOT NULL
);

CREATE INDEX idx_penalita_team ON penalita (team_id, stagione);


-- ============================================================
-- VISTE
-- ============================================================

CREATE VIEW roster_attuale AS
SELECT DISTINCT ON (g.id)
    g.id            AS giocatore_id,
    g.nome_common,
    g.nome_norm,
    t.team_id_a     AS team_id,
    t.tipo          AS ultimo_movimento,
    t.timestamp,
    c.importo,
    c.anni_originali,
    c.stagione_firma,
    c.tipo          AS tipo_contratto
FROM transazioni t
JOIN giocatori g ON g.id = t.giocatore_id
LEFT JOIN contratti c ON c.id = t.contratto_id AND c.attivo = TRUE
WHERE t.team_id_a IS NOT NULL
ORDER BY g.id, t.timestamp DESC;

CREATE VIEW ruolo_attuale AS
SELECT DISTINCT ON (giocatore_id, stagione)
    giocatore_id, team_id, stagione, ruolo_a AS ruolo, tipo, scadenza
FROM cambi_ruolo
ORDER BY giocatore_id, stagione, timestamp DESC;

CREATE VIEW firme AS
SELECT t.*, g.nome_common, g.nome_norm, c.importo, c.anni_originali
FROM transazioni t
JOIN giocatori g ON g.id = t.giocatore_id
LEFT JOIN contratti c ON c.id = t.contratto_id
WHERE t.tipo IN ('signed', 'rookie_firma', '10day_firma');
