# Lists Models

```
GET /models
```

Lists the currently available models, and provides basic information about each one such as the owner and availability. Check [Models & Pricing](</quick_start/pricing>) for our currently supported models.

## Responses

  * 200

OK, returns A list of models

  * application/json

  * Schema
  * Example (from schema)
  * Example

**

Schema

**

**object** stringrequired

**Possible values:** [`list`]

**

data

**

Model[]

required

  * Array [

**id** stringrequired

The model identifier, which can be referenced in the API endpoints.

**object** stringrequired

**Possible values:** [`model`]

The object type, which is always "model".

**owned_by** stringrequired

The organization that owns the model.

  * ]

```json
{  "object": "list",  "data": [    {      "id": "string",      "object": "model",      "owned_by": "string"    }  ]}
```

```json
{  "object": "list",  "data": [    {      "id": "deepseek-flash",      "object": "model",      "owned_by": "deepseek"    },    {      "id": "deepseek-v4-pro",      "object": "model",      "owned_by": "deepseek"    }  ]}
```

Loading...