
import csv
import os
import logging




class J1939Parser:
    def __init__(self, parameter_db_path='j1939_database.csv'):
        self.parameter_db = self._load_parameter_db(parameter_db_path)

    def _load_parameter_db(self, parameter_db_path):
        db = {}
        if not os.path.exists(parameter_db_path):
            logger.error(f"Parameter database file not found at {parameter_db_path}")
            return db

        with open(parameter_db_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                pgn = int(row['PGN'])
                spn = int(row['SPN'])
                if pgn not in db:
                    db[pgn] = {}
                db[pgn][spn] = {
                    'Name': row['Name'],
                    'StartByte': int(row['StartByte']),
                    'StartBit': int(row['StartBit']),
                    'BitLength': int(row['BitLength']),
                    'Resolution': float(row['Resolution']),
                    'Offset': float(row['Offset']),
                    'Unit': row['Unit']
                }
        return db

    def parse_data(self, pgn, data):
        parsed_values = {'code' : 0, 'pgn': pgn}
        if pgn not in self.parameter_db:
            parsed_values["msg"] = f"PGN {pgn} not found in database."
            parsed_values['code'] = -1
            return parsed_values

        for spn, param_info in self.parameter_db[pgn].items():
            start_byte = param_info['StartByte']
            start_bit = param_info['StartBit']
            bit_length = param_info['BitLength']
            resolution = param_info['Resolution']
            offset = param_info['Offset']
            unit = param_info['Unit']
            name = param_info['Name']

            # Ensure data is long enough for the parameter
            if start_byte >= len(data):
                parsed_values[name] = f"Data too short for SPN {spn} (requires byte {start_byte})"
                continue

            # Extract the relevant bytes
            # J1939 is little-endian
            value_bytes = bytearray()
            for i in range(bit_length // 8):
                if start_byte + i < len(data):
                    value_bytes.append(data[start_byte + i])
                else:
                    # Handle cases where data might be shorter than expected for multi-byte values
                    value_bytes.append(0x00) # Pad with zeros

            # Convert bytes to integer
            raw_value = int.from_bytes(value_bytes, byteorder='little')

            # Extract bits if bit_length is not byte-aligned or starts at a specific bit
            if bit_length % 8 != 0 or start_bit != 0:
                # Create a mask for the relevant bits
                mask = (1 << bit_length) - 1
                # Shift to align the start bit
                raw_value = (raw_value >> start_bit) & mask

            # Apply resolution and offset
            physical_value = (raw_value * resolution) + offset
            # parsed_values[name] = f"{physical_value:.2f} {unit}"
            parsed_values[name] = {
                'value' : physical_value,
                'unit' : unit
            }

        return parsed_values



if __name__ == "__main__":
    parser = J1939Parser()

    # Example 1: Engine Speed (PGN 61444, SPN 190)
    # Let's simulate a data frame where engine speed is 1000 RPM
    # 1000 / 0.125 = 8000. 8000 in hex is 0x1F40. Little endian: 0x40, 0x1F
    # So, data[3] = 0x40, data[4] = 0x1F
    engine_speed_data = bytearray([0x00, 0x00, 0x00, 0x40, 0x1F, 0x00, 0x00, 0x00])
    logger.info(f"\n--- J1939Parser Example --- ")
    logger.info(f"Parsing PGN 61444 with data: {engine_speed_data.hex()}")
    result_engine_speed = parser.parse_data(61444, engine_speed_data)
    logger.info(f"Result: {result_engine_speed}")
    logger.info("-" * 30)

    # Example 2: Wheel-Based Vehicle Speed (PGN 65265, SPN 84)
    # Let's assume vehicle speed is 60 km/h.
    # 60 km/h / 0.00390625 = 15360 (raw value)
    # Raw value 15360 in 16 bits (little endian) is 0x00, 0x3C
    # So, data[0] = 0x00, data[1] = 0x3C
    vehicle_speed_data = bytearray([0x00, 0x3C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    logger.info(f"Parsing PGN 65265 with data: {vehicle_speed_data.hex()}")
    result_vehicle_speed = parser.parse_data(65265, vehicle_speed_data)
    logger.info(f"Result: {result_vehicle_speed}")
    logger.info("-" * 30)

    # Example 3: PGN not in database
    logger.info("Parsing PGN 12345 (not in database)")
    result_not_found = parser.parse_data(12345, bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
    logger.info(f"Result: {result_not_found}")
    logger.info("-" * 30)

    # Example 4: Engine Percent Load At Current Speed (PGN 65265, SPN 164)
    # Let's assume engine load is 75%.
    # 75% / 1 = 75 (raw value)
    # Raw value 75 in 8 bits is 0x4B
    # So, data[4] = 0x4B
    engine_load_data = bytearray([0x00, 0x00, 0x00, 0x00, 0x4B, 0x00, 0x00, 0x00])
    logger.info(f"Parsing PGN 65265 with engine load data: {engine_load_data.hex()}")
    result_engine_load = parser.parse_data(65265, engine_load_data)
    logger.info(f"Result: {result_engine_load}")
    logger.info("-" * 30)
