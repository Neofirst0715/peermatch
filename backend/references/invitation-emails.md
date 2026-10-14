# Email texts

The invitation to a helper is built by `scripts/make_invite.py`. This file shows what it contains and holds the other texts.

## 1. Invitation to the helper (made by the script)

Subject: A fellow founder could use your experience

> Hi {first name},
>
> A fellow Volta founder is working on something where your experience could help.
>
> {invite_line}
>
> Would you be open to a 20-minute intro? If you say yes, I'll introduce you by name. If not, nothing happens and they won't know.
>
> To say yes, just reply YES to this email. Not a good time? You can ignore it.
>
> {Laura}
>
> (Ref: {need code}-{helper code})

The helper replies YES. A helper has at most one open invitation, so the reply already says which need it is about. The Ref line is a need code, never a name, and helps Laura search her inbox.

Why there is no "click here to say yes" link: a long `mailto:` link in a plain-text email is cut off by mail programs, so only the address becomes clickable and the subject and text are lost. A real button needs an HTML draft.

## 2. Introduction after a yes (made by `make_intro.py`)

Both people have agreed by now, so names and the founder's own wording are fine. It goes to both addresses at once. Laura can edit it before she sends.

Subject: Introduction: {founder name} and {helper name}

> Hi {founder first name} and {helper first name},
>
> {helper first name} has agreed to a 20-minute chat. Here is why I thought of you both:
>
> - {founder first name} is working on: {the founder's note, or their topics}
> - {helper first name} has: {the helper's note, or their topics}
>
> I'll leave you two to find a time. Thank you both.
>
> {Laura}

If a name or address is missing in the file, the script says so and stops. Nothing is invented.

## 3. Nothing to send when a helper says no

If a helper says "not now" or does not reply, nothing is sent to anyone. The founder is not told. The tracker moves to the next helper.
