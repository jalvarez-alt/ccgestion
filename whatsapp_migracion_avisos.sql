-- Migración para bases que ya tienen las tablas de WhatsApp (versión anterior, sin segundo aviso).
-- Ejecutar UNA sola vez en phpMyAdmin. Si una columna ya existe, MySQL avisa y se omite sin dañar nada.
-- (La app hace esto sola al abrir WhatsApp, si el usuario de la base tiene permiso ALTER.)

ALTER TABLE wa_campanas ADD COLUMN plantilla2 TEXT NULL;
ALTER TABLE wa_mensajes ADD COLUMN aviso TINYINT NOT NULL DEFAULT 1;
ALTER TABLE wa_mensajes ADD COLUMN manifiestos TEXT NULL;

CREATE TABLE IF NOT EXISTS wa_items (
  id INT AUTO_INCREMENT PRIMARY KEY,
  campana_id INT NOT NULL,
  telefono VARCHAR(20) NOT NULL,
  contacto VARCHAR(150) NULL,
  fecha DATE NULL,
  manifiesto VARCHAR(60) NOT NULL,
  placa VARCHAR(30) NULL,
  INDEX (campana_id), INDEX (telefono)
) CHARACTER SET utf8mb4;
