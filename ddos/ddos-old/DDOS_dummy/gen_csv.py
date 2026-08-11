import csv
import sqlite3


lookback = 5
window_size = 0.60


# Generate Table Name
#########################################################################################################################################
def gen_table_name(decode=False, table_name="", raw=False):
    global lookback
    global window_size

    if raw:
        return "L" + str(lookback) + "WS" + str(window_size)

    digit_mapping = {
        '0': 'Z',
        '1': 'O',
        '2': 'T',
        '3': 'T',
        '4': 'f',
        '5': 'F',
        '6': 's',
        '7': 'S',
        '8': 'E',
        '9': 'N',
        '.': 'P'
    }
    reversed_mapping = {value: key for key, value in digit_mapping.items()}

    if not decode:
        encoded_lookback = ''.join([digit_mapping[digit]
                                    for digit in str(lookback)])
        encoded_window_size = ''.join(
            [digit_mapping[digit] for digit in str(window_size)])
        return encoded_lookback + "D" + encoded_window_size
    else:
        decoded_lookback = table_name.split("D")[0]
        decoded_window_size = table_name.split("D")[1]
        decoded_lookback = int(
            ''.join([reversed_mapping[elem] for elem in decoded_lookback]))
        decoded_window_size = float(
            ''.join([reversed_mapping[elem] for elem in decoded_window_size]))
        return decoded_lookback, decoded_window_size

#################################################################################################################################################
# Generate Query


def generate_query():
    tabel_name = gen_table_name()
    query = 'SELECT '
    if lookback > 1:
        for column in range(lookback):
            column_name = 'c' + str(column)
            query += column_name + ', '
    query += 'label FROM ' + tabel_name
    print(query)
    return query


##################################################################################################################################################
# Fetch Data


def get_data():
    query = generate_query()
    conn = sqlite3.connect('input.db')
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return rows, [description[0] for description in cursor.description]
##################################################################################################################################################
# Save as CSV


def gen_csv_dump():

    csv_file = "processed_data.csv"
    data, column_names = get_data()
    with open(csv_file, 'w', newline='') as file:
        csv_writer = csv.writer(file)

        # Write the header (column names) to the CSV file
        csv_writer.writerow(column_names)

        # Write the data rows to the CSV file
        csv_writer.writerows(data)

##################################################################################################################################################


if __name__ == "__main__":
    gen_csv_dump()
