create table ausg.public.tracking_thread
(
    id           serial
        primary key,
    channel      varchar(20),
    ts           varchar(100),
    body         text,
    enabled      boolean              default true not null,
    reg_ts   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    upd_ts   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

