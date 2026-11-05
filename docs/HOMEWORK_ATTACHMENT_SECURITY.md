# Homework attachment security and staging checklist

## Data flow
1. An authenticated student with an existing submission requests an upload URL through FastAPI.
2. FastAPI re-resolves the active student portal identity and checks the submission belongs to that student and school.
3. FastAPI creates an unpredictable object path and requests a one-object signed upload URL from the private `homework-private` bucket. The Supabase secret key is used only server-side.
4. The browser uploads directly to the signed URL. The bucket rejects files over 10 MiB and content types outside the explicit allow-list.
5. The student calls the completion endpoint. FastAPI performs a Storage HEAD request and compares the stored byte size and MIME type with the request metadata before marking the attachment ready.
6. A student, verified parent, currently assigned teacher, owner or headmaster can request a five-minute signed download URL only after the API re-checks school, learner, guardian and class permissions.

## Limits and accepted types
- Maximum 10 MiB per file and five attachments per submission.
- PDF, DOCX, XLSX, PPTX, JPEG, PNG and plain text only.
- Original filenames are display metadata only. Object keys use generated UUIDs and never contain user-provided path segments.
- No overwrite is permitted. Each upload gets a unique object path.
- Pending uploads are not exposed in listing responses. A pending upload is not considered submitted/available until Storage metadata has been verified.

## Security boundaries
- Bucket is private; public object URLs are not used.
- Browser code never receives the Supabase secret/service key.
- Application authorization remains authoritative; signed URLs are issued only after per-request authorization.
- Parent access re-checks active, verified guardian linkage.
- Teacher access re-checks the current class assignment and assignment ownership.
- Object metadata is tenant-scoped through composite foreign keys. The public Data API receives no direct grants on attachment metadata.
- Signed upload URLs are bearer capabilities and are valid for up to two hours; download URLs are limited to five minutes. Do not log or persist signed URLs.

## Staging validation required before release
- Apply and review the proposed homework migration on staging only.
- Confirm the bucket is private, has the 10 MiB limit and MIME allow-list, and does not have permissive Storage policies.
- Verify the Storage signed-upload response format and signed-download response format for the deployed Supabase version.
- Test browser PUT upload CORS and the HEAD metadata response.
- Test wrong-size and wrong-MIME uploads, expired upload URLs, duplicate attempts, five-file limit, missing objects and orphaned pending objects.
- Test cross-school, unrelated-student, unverified-parent and revoked-teacher-assignment download denial.
- Confirm all signed URLs expire as expected and are absent from application logs.
- Add a cleanup job for abandoned pending uploads only after retention and audit requirements are agreed.

## Release status
This is a feature-branch implementation. The proposed migration is unapplied. Do not deploy the attachment endpoints or enable the feature until staging validation is complete.
