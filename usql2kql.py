from pathlib import Path
import re
import argparse
import time

# Este projecto fue creado para limpiar el código USQL de un projecto.
# No voy a pegar la licencia ya que confío quienes los que lo van a usar.
#
# Funcionamiento:
# En KQL no se admiten los `CROSS JOIN` por lo que ten cuidado
#
# Introduce el nombre del archivo como argumento tal que así:
# `python usql2kql.py **archivo.usql**`
#
# También puedes cambiarle el nombre del output:
# `python usql2kql.py **archivo.usql** **salida.kql**`

parser = argparse.ArgumentParser(
    prog="USQL2KQL", description="Convert U-SQL to KQL")
parser.add_argument("input_file", type=str, help="Input U-SQL file")
parser.add_argument(
    "output_file", nargs="?", type=str, default=None, help="Output KQL file"
)

args = parser.parse_args()

input_file = args.input_file
output_file = args.output_file or f"./{Path(input_file).stem}.kql"

if __name__ == "__main__":
    start_time = time.time()

    with open(input_file, "r") as f:
        input_code = f.read()

    # Overwrite the code in case it's not empty
    with open(output_file, "w") as f:
        f.write("")
        
    # Remove multiline comments
    input_code = re.sub(r'/\*.*?\*/', '', input_code, flags=re.DOTALL)
    # Remove inline comments
    input_code = re.sub(r'//.*?$', '', input_code, flags=re.MULTILINE)

    input_code = input_code.split(";")[:-1]
    
    # Sanitize empty lines
    input_code = [item for item in input_code if item != ""]
    
    for code in input_code:
        def process_list(input_list):
            return "\n".join(
                item
                .replace("==", " == ")
                .replace("+", " + ")
                .replace("-", " - ")
                .replace("*", " * ")
                .replace("/", " / ")
                .replace(":", " : ")
                .strip()
                for item in input_list
                if item.strip()
            )
        code = process_list(code.split("\n"))

        # Define the list of keywords
        keywords = (
            "SELECT",
            "FROM",
            "INNER JOIN",
            "LEFT JOIN",
            "LEFT OUTER JOIN",
            "RIGHT JOIN",
            "RIGHT OUTER JOIN",
            "FULL JOIN",
            "FULL OUTER JOIN",
            "CROSS JOIN",
            "ORDER BY",
            "WHERE",
            "GROUP",
            "UNION",
        )

        # Iterate through the keywords and remove extra spaces
        for keyword in keywords:
            aligned_query = re.sub(r"\b{0}\b".format(keyword), keyword, code)

        def split_aligned_query(aligned_query, keywords):
            pattern = "|".join(map(re.escape, keywords))
            return re.sub(pattern, lambda x: f"\n{x.group(0)}", aligned_query)

        # Remove line breaks and extra spaces
        aligned_query = split_aligned_query(
            re.sub(r"\s+", " ", aligned_query).strip(), keywords
        )

        var_text = ""
        find_var = re.match(r"@(\w+)\s*=\s*", aligned_query)
        if find_var:
            var_text = f"let {find_var.group(1)} ="

        def extract_join_table(join_str, join_type):
            # Split the line into tokens
            len_jt = join_type.split(" ")
            len_jt = len(len_jt)
            jt = join_str.split(" ")[len_jt]
            
            pattern = re.compile(r'(?:\[)?(\w+)(?:\])?(?:\.(\[)?(\w+)(?:\])?)*')
            result = pattern.search(jt)
            return result.group(result.lastindex) if result else None

        def parse_sql(aligned_query):
            sql_props = {
                "main_table": "",
                "as": "",
                "body": {"join": []},
                "select": [],
            }

            # Get FROM statement
            from_pattern = re.compile(
                r"FROM (@?.+)(?: AS (\w+))", re.IGNORECASE)
            from_match = from_pattern.search(aligned_query)
            if from_match:
                main_table = from_match.group(1)
                main_table = main_table.lstrip("@")
                
                pattern = re.compile(r'(?:\[)?(\w+)(?:\])?(?:\.(\[)?(\w+)(?:\])?)*')
                result = pattern.search(main_table)
                new_main_table = result.group(result.lastindex) if result else None
                 
                # Set to empty string if None
                as_name = from_match.group(2) or ""
                sql_props["main_table"] = new_main_table
                sql_props["as"] = as_name

            # Get OTHER statement
            for line in aligned_query.split("\n"):
                sql_pattern = re.compile(
                    r"\b(FROM|INNER JOIN|LEFT JOIN|LEFT OUTER JOIN|RIGHT JOIN|RIGHT OUTER JOIN|FULL JOIN|FULL OUTER JOIN|CROSS JOIN|WHERE|ORDER BY|GROUP BY|UNION)\b"
                )
                sql_kws = sql_pattern.findall(line)
                for kw in sql_kws:
                    if kw in keywords[2:10]:
                        sql_props["body"]["join"].append(
                            {
                                "kind": kw.lower(),
                                "table": extract_join_table(line, kw),
                                "as": re.search(r"AS (\w+)", line, re.IGNORECASE).group(
                                    1
                                )
                                if re.search(r"AS (\w+)", line, re.IGNORECASE)
                                else None,
                                "on": re.search(r"ON (.*)", line, re.IGNORECASE).group(
                                    1
                                ),
                            }
                        )
                    elif "WHERE" == kw:
                        where_condition = re.search(
                            r"WHERE (.*)", line, re.IGNORECASE | re.DOTALL
                        )
                        if where_condition:
                            sql_props["body"]["where"] = where_condition.group(
                                1)
                    elif "ORDER BY" == kw:
                        order_condition = re.search(
                            r"ORDER BY (.*)", line, re.IGNORECASE | re.DOTALL
                        )
                        if order_condition:
                            sql_props["body"]["order"] = order_condition.group(
                                1)
                    elif "GROUP BY" == kw:
                        union_condition = re.search(
                            r"GROUP BY (.*)", line, re.IGNORECASE | re.DOTALL
                        )
                        if union_condition:
                            sql_props["body"]["summarize"] = union_condition.group(
                                1)
                    elif "UNION" == kw:
                        union_condition = re.search(
                            r"UNION (.*)", line, re.IGNORECASE | re.DOTALL
                        )
                        if union_condition:
                            sql_props["body"]["union"] = union_condition.group(
                                1)

                select_pattern = re.compile(
                    r"SELECT (.*?)(?:FROM|$)", re.IGNORECASE | re.DOTALL
                )
                select_match = select_pattern.search(line)

                if select_match:

                    def split_with_parentheses(s):
                        result = []
                        stack = []
                        current = []

                        for char in s:
                            if char == "," and not stack:
                                result.append("".join(current).strip())
                                current = []
                            else:
                                current.append(char)
                                if char == "(":
                                    stack.append("(")
                                elif char == ")" and stack:
                                    stack.pop()

                        if current:
                            result.append("".join(current).strip())

                        return result

                    def extract_columns_and_aliases(input_string):
                        chunks = split_with_parentheses(input_string)

                        result = []
                        for chunk in chunks:
                            # Split at " AS " and capture both sides
                            split_chunk = re.split(r"\s+AS\s+", chunk)

                            if len(split_chunk) == 1:
                                result.append([split_chunk[0]])
                            elif len(split_chunk) == 2:
                                result.append([split_chunk[0], split_chunk[1]])
                            else:
                                result.append([chunk])

                        return result

                    sql_props["select"] = extract_columns_and_aliases(
                        select_match.group(1)
                    )

            return sql_props

        sql_props = parse_sql(aligned_query)

        kql_output = ""
        tab = " " * 2
        main_table = sql_props["main_table"]
        short_table = sql_props["as"]
        body = sql_props["body"]
        select = sql_props["select"]

        if var_text != "":
            kql_output += var_text + "\n"

        def to_var(s):
            return re.compile(r"\b(\w+\.\w+)\b").sub(r"['\1']", s)

        # Project
        sum_list = []
        if select is not []:
            project_kql_output = ""
            project_kql_output += f"{tab}| project\n"

            def replace_text_inside_brackets(sentence_list):
                for i in range(len(sentence_list)):
                    sentence_data = sentence_list[i]

                    for j in range(len(sentence_data)):
                        if "[" in sentence_data[j] and "]" in sentence_data[j]:
                            # Extract the text inside brackets
                            start_index = sentence_data[j].find("[")
                            end_index = sentence_data[j].find("]")
                            text_inside_brackets = sentence_data[j][
                                start_index + 1: end_index
                            ]

                            # Replace the brackets and the text inside with just the text inside
                            sentence_data[j] = sentence_data[j].replace(
                                f"[{text_inside_brackets}]", text_inside_brackets
                            )

            replace_text_inside_brackets(select)

            namify_array = [
                "{0} = {1}".format(item[1], to_var(item[0]))
                if len(item) == 2
                else f"{item[0][len(short_table)+1:] if item[0].startswith(short_table + '.') else to_var(item[0])}"
                for item in select
            ]

            for i, namify in enumerate(namify_array):
                # Regex patterns
                def coalesce(input_str):
                    return re.sub(
                        r'(\[?[\'"]?[\w\.]+[\'"]?\]?)\s*\?\?\s*(\S+)',
                        r"coalesce(\1, \2)",
                        input_str,
                    )

                namify = coalesce(namify)

                def parse_sum_function(line):
                    match_var = re.match(
                        r"\s*([a-zA-Z_]\w*)\s*=\s*(?!SUM)([^#]*)", line
                    )
                    match_sum = re.match(r"\s*SUM\(([^)]+)\)\s*", line)

                    if match_var and "SUM" in line:
                        variable_name = match_var.group(1)

                        get_var = re.search(r"SUM\((.*?)\)", line)
                        get_var = get_var.group(1) if get_var else None

                        sum_list.append(variable_name)
                        return f"{variable_name} = {get_var}"
                    elif match_sum:
                        var = match_sum.group(1)
                        sum_list.append(var)
                        return var
                    else:
                        return line

                namify = parse_sum_function(namify)

                def case(input_string):
                    assignment_pattern = re.compile(
                        r"([^ ]+)\s*=\s*CASE\s+([^ ]+).*?END"
                    )
                    assignment_match = assignment_pattern.search(input_string)

                    if assignment_match:
                        result_column = assignment_match.group(1)
                        case_column = assignment_match.group(2)
                        pattern = re.compile(
                            r'WHEN\s+(\S+)\s+THEN\s+("([^"]*)"|\S+)')
                        when_then_matches = pattern.findall(input_string)

                        cases = tab * 2 + f",\n{tab*3}".join(
                            f"{case_column} == {when}, {result}"
                            for when, result, _ in when_then_matches
                        )

                        return result_column + " = case(\n{}\n{})".format(
                            tab + cases, tab * 2
                        )
                    else:
                        return "Invalid input: Unable to determine column name"

                if all(string in namify for string in ("CASE", "WHEN", "THEN")):
                    namify = case(namify)

                namify = re.sub(r'\(decimal\) (\d+)', r'todecimal(\1)', namify)

                # Replace function keys
                function_mapping = {
                    "CONCAT": "strcat",
                    "SUBSTRING": "substring",
                    "String.Concat": "strcat",
                }
                pattern = re.compile(
                    r"\b(" + "|".join(function_mapping.keys()) + r")\b"
                )
                replaced_string = pattern.sub(
                    lambda x: function_mapping[x.group()], namify
                )
                namify = re.sub(r"\s*\(\s*", "(", replaced_string)

                for v in function_mapping.values():
                    namify = namify.replace(f"['{v}']", v)

                # Special functions
                def replace_match(match):
                    if match.group(2) == "Substring":
                        if match.group(1).startswith(", "):
                            return (
                                f", substring({match.group(1)[2:]}, {match.group(3)})"
                            )
                        else:
                            return f"substring({match.group(1)}, {match.group(3)})"
                    return match.group(0)

                # Define the regex pattern for matching the specified format
                pattern = re.compile(
                    r"(\[?\'?[^\'\]]+\'?\]?)\.(\w+)\(([^)]+)\)")

                # Use the sub method to replace matches according to the defined function
                namify = pattern.sub(replace_match, namify)

                # Conditional operator
                def modify_code(original_code):
                    parts = original_code.split("?")
                    condition_part = parts[1].split(":")
                    return (
                        "iff("
                        + ", ".join([parts[0], condition_part[0],
                                    condition_part[1]])
                        + ")"
                    )

                if "?" in namify and ":" in namify:
                    namify = modify_code(namify)

                project_kql_output += (
                    tab * 2 + namify +
                    (",\n" if len(namify_array) != i + 1 else "\n;")
                )

        # Body
        join_kql_output = ""
        where_kql_output = ""
        order_kql_output = ""
        summarize_kql_output = ""
        summarize_by_kql_output = ""
        union_kql_output = ""
        for type, content in body.items():
            if "join" in type:
                for join in content:
                    j_kind = join["kind"]
                    j_table = join["table"]
                    j_as = join["as"]
                    j_on = join["on"]

                    cond_text = f"AS {j_as} ON "
                    if j_on.startswith(cond_text):
                        join["on"] = j_on[len(cond_text):]
                        j_on = join["on"]

                    # Removes square brackets
                    def extract_table(input_string):
                        parts = input_string.split(".")
                        last_item = parts[-1]

                        if "[" in last_item:
                            match = re.search(r"\[([^\]]+)\]", last_item)
                            return match.group(1) if match else None
                        else:
                            return last_item

                    j_table = extract_table(j_table)

                    if j_kind == "cross join":
                        join_kql_output += '// "cross join" is not a valid join\n'
                        continue

                    join_kql_output += f'{tab}| join kind='

                    join_mapping = {
                        "inner join": "inner",
                        "left join": "leftsemi",
                        "right join": "rightsemi",
                        "left outer join": "leftouter",
                        "right outer join": "rightouter",
                        "full join": "fullouter",
                        "full outer join": "fullouter",
                    }

                    if j_kind in join_mapping:
                        join_kql_output += join_mapping[j_kind] + ' '

                    # Get variables from `project`
                    project_keys = list(
                        set(re.findall(r"\['(.*?)'\]", project_kql_output))
                    )
                    project_keys = tuple(
                        item for item in project_keys if item.startswith(f"{j_as}.")
                    )
                    if len(project_keys) > 0:
                        join_kql_output += f"(\n"
                        join_kql_output += f"{tab*2}{j_table}\n"
                        join_kql_output += f"{tab*2}| project-rename // {j_as}\n"

                        # Get keys from select
                        for i, key in enumerate(project_keys):
                            join_kql_output += (
                                f"{tab*3}['{key}']="
                                + key[len(j_as) + 1:]
                                + ("" if len(project_keys) == i + 1 else ",")
                                + "\n"
                            )

                    # On format
                    j_on = re.sub(
                        r"\b and \b", f"\n{tab*2}and ", j_on, flags=re.IGNORECASE
                    )
                    j_on = re.sub(
                        r"\b or \b", f"\n{tab*2}or ", j_on, flags=re.IGNORECASE
                    )

                    join_project_keys = []

                    def format_line(text, tab):
                        if tab != "":
                            text = re.sub(r"\b" + tab + r"\.", "", text)
                        join_project_keys.extend(re.split(r"\s*==\s*", text))
                        left, right = re.split(r"\s*==\s*", text)

                        if not re.match(r"{tab}\.\w+$", text) or re.match(
                            r"^{curr_table}\.\w+", text
                        ):
                            temp = right
                            right = left
                            left = temp
                        if re.compile(r"^\w+\.\w+$").match(left):
                            left = f"['{left}']"
                        if re.compile(r"^\w+\.\w+$").match(right):
                            right = f"['{right}']"

                        # Generate the desired output format with square brackets
                        return f"['$left'].{left} == ['$right'].{right}"

                    pattern = pattern = re.compile(
                        r"\s*(==|\b(?:and|or)\b|[^\s=]+(?:\s*==\s*[^\s=]+)?)\s*"
                    )
                    j_on_iterate = pattern.findall(j_on)

                    for i, j in enumerate(j_on_iterate):
                        if i % 2 == 0:
                            j_on_iterate[i] = format_line(j, short_table)

                    j_on = " ".join(j_on_iterate)
                    j_on = j_on.replace(" and ", f" and\n{tab*2}").replace(
                        " or ", f" or\n{tab*2}"
                    )

                    join_project_keys = tuple(
                        item
                        for item in join_project_keys
                        if item.startswith(f"{j_as}.")
                    )
                    if len(join_project_keys) > 0:
                        if len(project_keys) == 0:
                            join_kql_output += f"(\n"
                            join_kql_output += f"{tab*2}{j_table}\n"
                            join_kql_output += f"{tab*2}| project-rename // {j_as}\n"

                        # Get keys from select
                        for i, key in enumerate(join_project_keys):
                            if not key in project_keys:
                                join_kql_output += (
                                    f"{tab*3}['{key}']="
                                    + key[len(j_as) + 1:]
                                    + ("" if len(join_project_keys)
                                       == i + 1 else ",")
                                    + "\n"
                                )
                    if len(project_keys) > 0 or len(join_project_keys) > 0:
                        join_kql_output += f"{tab}) "
                    join_kql_output += f"on {j_on}\n"
            elif type == "where":
                content = content.replace(
                    " AND ", " and ").replace(" OR ", " or ")
                where_kql_output += f"{tab}| where\n{tab*2}{content}\n"
            elif type == "order":
                order_kql_output += f"{tab}| sort by {content}\n".replace(
                    "ASC", "asc"
                ).replace("DESC", "desc")
            elif type == "union":
                union_kql_output += f"{tab}| union "
                union_kql_output += "// " + content + "\n"
            elif type == "summarize":
                summarize_kql_output += f"{tab}| summarize "
                summarize_by_kql_output += f"by {content}"

        if len(sum_list) > 0:
            if summarize_kql_output == "":
                summarize_kql_output += f"{tab}| summarize "
            for i, item in enumerate(sum_list):
                summarize_kql_output += f"{item} = sum({item})" + (
                    ", " if len(sum_list) > i + 1 else " "
                )
            sum_list = []
        summarize_by_kql_output += "\n" if summarize_by_kql_output else ""

        # Print order
        
        if main_table == "":
            if kql_output == "":
                pass
        else:
            kql_output += (
                f"{main_table}" +
                (f" // {short_table}" if short_table else "") + "\n"
            )
            kql_output += join_kql_output
            kql_output += where_kql_output
            kql_output += order_kql_output
            kql_output += summarize_kql_output + summarize_by_kql_output
            kql_output += union_kql_output
            kql_output += project_kql_output
            kql_output += "\n"

        with open(output_file, "a") as f:
            f.write(kql_output)

    end_time = time.time()
    execution_time = end_time - start_time

    print(f"Took {execution_time:.4f} seconds to run.")
