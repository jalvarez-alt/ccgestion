-- Corrige la hora de los datos de WhatsApp guardados ANTES del ajuste a hora de Colombia.
-- Hasta el 19/10/2026 el servidor guardaba la hora de Nueva York (EDT, UTC-4): 1 hora ADELANTADA respecto a Bogotá (UTC-5).
-- EJECUTAR UNA SOLA VEZ en phpMyAdmin (base aqreqjec_ccgestion). Si se ejecuta dos veces, resta 2 horas.
-- Antes de ejecutarlo, haz un respaldo (phpMyAdmin > Exportar) y confirma que lo antiguo se ve 1 hora adelantado.

UPDATE wa_campanas   SET creada_en    = creada_en    - INTERVAL 1 HOUR;
UPDATE wa_mensajes   SET creado_en    = creado_en    - INTERVAL 1 HOUR,
                         enviado_en   = enviado_en   - INTERVAL 1 HOUR,
                         entregado_en = entregado_en - INTERVAL 1 HOUR,
                         leido_en     = leido_en     - INTERVAL 1 HOUR;
UPDATE wa_respuestas SET recibida_en  = recibida_en  - INTERVAL 1 HOUR;
