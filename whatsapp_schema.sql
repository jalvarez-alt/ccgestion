-- Esquema de WhatsApp (campañas, mensajes, respuestas con adjunto en OneDrive). Es idempotente.
-- Lo crea sola la app al abrir WhatsApp por primera vez; este archivo sirve para aplicarlo a mano (phpMyAdmin).

CREATE TABLE IF NOT EXISTS `wa_campanas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(150) NOT NULL,
  `plantilla` text NOT NULL,
  `creada_por` varchar(150) DEFAULT NULL,
  `creada_en` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `wa_mensajes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `campana_id` int(11) NOT NULL,
  `manifiesto` varchar(60) DEFAULT NULL,
  `cliente` varchar(200) DEFAULT NULL,
  `orden_cargue` varchar(60) DEFAULT NULL,
  `remesa` varchar(60) DEFAULT NULL,
  `contacto` varchar(150) DEFAULT NULL,
  `telefono` varchar(20) NOT NULL,
  `texto` text NOT NULL,
  `estado` varchar(12) NOT NULL DEFAULT 'pendiente',
  `wa_id` varchar(120) DEFAULT NULL,
  `error` varchar(255) DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  `enviado_en` datetime DEFAULT NULL,
  `entregado_en` datetime DEFAULT NULL,
  `leido_en` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `campana_id` (`campana_id`),
  KEY `telefono` (`telefono`),
  KEY `wa_id` (`wa_id`),
  KEY `manifiesto` (`manifiesto`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `wa_respuestas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mensaje_id` int(11) DEFAULT NULL,
  `telefono` varchar(20) NOT NULL,
  `texto` text DEFAULT NULL,
  `tipo` varchar(20) NOT NULL DEFAULT 'chat',
  `wa_id` varchar(120) DEFAULT NULL,
  `recibida_en` datetime NOT NULL,
  `archivo_estado` varchar(12) DEFAULT NULL,
  `archivo_nombre` varchar(255) DEFAULT NULL,
  `archivo_url` varchar(800) DEFAULT NULL,
  `archivo_error` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_wa_id` (`wa_id`),
  KEY `mensaje_id` (`mensaje_id`),
  KEY `telefono` (`telefono`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Estado del servicio de WhatsApp (latido). La app también la crea sola si falta.
CREATE TABLE IF NOT EXISTS `wa_servicio` (
  `id` tinyint(4) NOT NULL,
  `estado` varchar(20) NOT NULL,
  `qr` mediumtext DEFAULT NULL,
  `numero` varchar(30) DEFAULT NULL,
  `en_cola` int(11) NOT NULL DEFAULT 0,
  `comando` varchar(20) DEFAULT NULL,
  `actualizado` datetime NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
