> [!WARNING]
> **This tool doesn't achieve a 100% code translation as it serves as a helpful aid.**
> 
> It works using a specific script and might not be perfect, but it's handy for dealing with similar structures.\
> Additionally, it's crucial to have `AS` after `FROM`. So ensure to add this keyword if not present.

> [!NOTE]
> This tool was developed for migrating **U-SQL** code to **KQL** code, using a **JSON** structure and then assembling it with it's correct order.
> 
> **KQL** incorporates the following function for translate **raw SQL** code:
> ``` kusto
> --
> explain
> -- YOUR SQL CODE GOES HERE
> ```
> Learn more on: https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/sqlcheatsheet

**CORRECT**
``` sql
SELECT ...
FROM foo AS bar;
```

**INCORRECT**
``` sql
SELECT ...
FROM foo bar;
```

``` sql
SELECT ...
FROM foo;
```
