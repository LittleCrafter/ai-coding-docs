# Delete File

```
DELETE /files/:file_id
```

Deletes a file.

## Request

### 

Path Parameters

**file_id** stringrequired

The ID of the file to delete.

## Responses

  * 200

OK, returns the deletion status.

  * application/json

  * Schema
  * Example (from schema)
  * Example

**

Schema

**

**id** stringrequired

The ID of the deleted file.

**object** stringrequired

**Possible values:** [`file`]

The object type, which is always `file`.

**deleted** booleanrequired

Whether the file was successfully deleted.

```json
{  "id": "string",  "object": "file",  "deleted": true}
```

```json
{  "id": "file-api-0a1b2c3d4e5f60718293a4b5c6d7e8f9",  "object": "file",  "deleted": true}
```

Loading...