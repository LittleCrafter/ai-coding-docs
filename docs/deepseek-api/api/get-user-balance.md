# Get User Balance

Copy MarkdownCopy Markdown

[Open Markdown](<https://api-docs.deepseek.com/api/get-user-balance.md> "Open Markdown in a new tab")

```
GET /user/balance
```

Get user current balance

## Responses

**200**

OK, returns user balance info.

**application/json**

**Schema**

**

Schema

**

**is_available** boolean

Whether the user's balance is sufficient for API calls.

**

balance_infos

**

object[]

  * Array [

**currency** string

**Possible values:** `CNY`, `USD`

The currency of the balance.

**total_balance** string

The total available balance, including the granted balance and the topped-up balance.

**granted_balance** string

The total not expired granted balance.

**topped_up_balance** string

The total topped-up balance.

  * ]

**Example**

```json
{
  "is_available": true,
  "balance_infos": [
    {
      "currency": "CNY",
      "total_balance": "110.00",
      "granted_balance": "10.00",
      "topped_up_balance": "100.00"
    }
  ]
}
```

Loading...