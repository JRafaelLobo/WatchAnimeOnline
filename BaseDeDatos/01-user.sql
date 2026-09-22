USE AnimeDB;
GO

CREATE TABLE ratings (
    userId BIGINT NOT NULL,
    movieId BIGINT NOT NULL,
    rating FLOAT NOT NULL,
    [timestamp] BIGINT NULL,

    CONSTRAINT PK_ratings
        PRIMARY KEY (userId, movieId)
);
GO

USE AnimeDB;
GO

CREATE TABLE Usuarios (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nombre NVARCHAR(100) NOT NULL,
    email NVARCHAR(255) NOT NULL UNIQUE,
    password_hash NVARCHAR(500) NOT NULL,
    fecha_creacion DATETIME2 NOT NULL
        DEFAULT SYSDATETIME()
);
GO