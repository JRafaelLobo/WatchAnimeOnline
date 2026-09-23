/* =========================================================
   BASE DE DATOS
   ========================================================= */

USE AnimeDB;
GO


/* =========================================================
   TABLA: ratings
   ========================================================= */

IF OBJECT_ID(N'dbo.ratings', N'U') IS NULL
CREATE TABLE ratings
(
    userId      BIGINT NOT NULL,
    movieId     BIGINT NOT NULL,
   rating      FLOAT NOT NULL,
    [timestamp] BIGINT NULL,

    CONSTRAINT PK_ratings
        PRIMARY KEY (userId, movieId)
);
GO


/* =========================================================
   TABLA: Usuarios
   ========================================================= */

IF OBJECT_ID(N'dbo.Usuarios', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.Usuarios', N'username') IS NULL
BEGIN
   EXEC sp_rename N'dbo.Usuarios', N'Usuarios_legacy';
END
GO

IF OBJECT_ID(N'dbo.Usuarios', N'U') IS NULL
CREATE TABLE Usuarios
(
    username         VARCHAR(16) NULL,
    user_id          BIGINT NULL,
    stats_mean_score DECIMAL(15,1) NULL
);
GO


/* =========================================================
   TABLA: Animes
   ========================================================= */

IF OBJECT_ID(N'dbo.Animes', N'U') IS NULL
CREATE TABLE Animes
(
    anime_id        BIGINT NULL,

    title           VARCHAR(500) NULL,
    title_english   VARCHAR(500) NULL,
    image_url       VARCHAR(60) NULL,
    type            VARCHAR(7) NULL,
    source          VARCHAR(100) NULL,

    episodes        BIGINT NULL,
    status          VARCHAR(16) NULL,
    aired_string    VARCHAR(28) NULL,
    duration        VARCHAR(15) NULL,
    rating          VARCHAR(30) NULL,

    score           DECIMAL(15,1) NULL,
    scored_by       BIGINT NULL,
    rank            DECIMAL(15,1) NULL,
    popularity      BIGINT NULL,
    members         BIGINT NULL,
    favorites       BIGINT NULL,

    premiered       VARCHAR(11) NULL,

    -- Tamaños ampliados
    producer        VARCHAR(1000) NULL,
    studio          VARCHAR(500) NULL,

    genre           VARCHAR(93) NULL,
    duration_min    DECIMAL(15,1) NULL,
    aired_from_year DECIMAL(15,1) NULL
);
GO


/* =========================================================
   TABLA: Reviews
   ========================================================= */

IF OBJECT_ID(N'dbo.Reviews', N'U') IS NULL
CREATE TABLE Reviews
(
    anime_id BIGINT NULL,
    my_score BIGINT NULL,
    user_id  BIGINT NULL
);
GO


/* =========================================================
   TABLA: auth_users
   Credenciales de la API; no forma parte del ETL de Apache Hop.
   ========================================================= */

IF OBJECT_ID(N'dbo.auth_users', N'U') IS NULL
CREATE TABLE auth_users
(
   id              INT IDENTITY(1,1) PRIMARY KEY,
   nombre          NVARCHAR(100) NOT NULL,
   email           NVARCHAR(255) NOT NULL UNIQUE,
   password_hash   NVARCHAR(500) NOT NULL,
   fecha_creacion  DATETIME2 NOT NULL DEFAULT SYSDATETIME()
);
GO