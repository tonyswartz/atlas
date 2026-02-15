# Bambu Lab Printer Specifications

## Printer Model
**Bambu Lab X1-Carbon**
- 4-color AMS (Automatic Material System)
- FTPS access enabled
- Network hostname: `printer.local`

## FTP Paths
- Metadata: `/data/Metadata/`
- Active job file: Varies by source
  - BambuStudio: `/data/Metadata/[filename].gcode`
  - Handy app: `/data/Metadata/plate_1.gcode`
  - SD card: `/data/Metadata/[filename].gcode`

## Filament Tracking
- JeevesUI database tracks spools
- Each spool: ID, type, color, remaining grams, $/g cost
- Logging format: spool_id, grams_used, print_name, user_name

## BambuBuddy Integration
- SQLite DB: `~/apps/bambuddy/bambuddy.db`
- Table: `print_archives`
- Fields: print_id, start_time, end_time, filename, filament_type, filament_color, weight_grams
- All print sources logged here (BambuStudio, Handy app, SD card)

## Reply Format
**Single spool:**
```
6, 39g, Tony
```

**Multi-color (multiple spools):**
```
5, 42g + 8, 18g, Tony
```

**Prefilled (when only name needed):**
```
Tony
```

## Common Filament Types
- PLA (PolyTerra, PolyLite, Bambu)
- PETG (Bambu, PolyLite)
- ABS (rare usage)
- TPU (flexible, occasional)

## Typical Print Weights
- Small parts: 5-20g
- Medium prints: 30-80g
- Large prints: 100-300g
- Multi-part assemblies: 200-500g
