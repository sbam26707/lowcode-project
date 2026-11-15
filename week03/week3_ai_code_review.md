# Week 3 --- AI Code Review

Reviewed by: ChatGPT (GPT-6)    Date: 15 November 2026

**Source reviewed:** `it-investment-tracker.zip` (Flask application
source).\
**Review method:** Static code inspection. No penetration test or
runtime exploit testing was performed. "Yes" means the issue is
supported by the source code; it does not necessarily mean an exploit
was demonstrated.

## Findings

  ---------------------------------------------------------------------------------------------------------------------
  \#             File:line            What it says is   Is it real?                         Action
                                      wrong                                                 
  -------------- -------------------- ----------------- ----------------------------------- ---------------------------
  1              `app.py:1092–1105`   SQL query is      Partly --- SQL fragments are        **LEAVING** --- not an
                                      assembled partly  concatenated, but submitted values  exploitable SQL injection
                                      through string    are passed as SQL parameters. No    finding. Keep values
                                      concatenation     SQL injection was demonstrated.     parameterised.
                                      (`sql +=`).                                           

  2              `app.py:16`          Flask secret key  Yes ---                             **LEAVING** for local demo
                                      has a hardcoded   `poc-demo-only-not-a-real-secret`   only. Before deployment,
                                      fallback value.   is used when the `SECRET_KEY`       require a strong secret
                                                        environment variable is absent.     from
                                                                                            environment/configuration
                                                                                            and do not provide a known
                                                                                            fallback.

  3              `app.py:70–71`,      No server-side    Yes --- `form_str()` strips         **COMPLETE** --- add maximum
                 `550–560`            maximum length    whitespace but does not enforce     lengths on the server and
                                      validation for    length limits; the overview route   align database column
                                      investment name   checks that the name is non-empty   constraints if appropriate.
                                      or description.   and unique, not its length.         Test boundary and
                                                                                            over-limit values.

  4              `app.py:1111–1112`   Flask is started  Yes --- explicitly enabled in the   **LEAVING** for local
                                      with              `__main__` run block.               development only. Disable
                                      `debug=True`.                                         debug mode in any deployed
                                                                                            environment and use a
                                                                                            production WSGI server.

  5              `app.py:212–216`     Database is       Yes --- the handler commits         **TO DO** --- define
                                      committed in      whenever `g` contains a database    transaction boundaries for
                                      `after_request`   connection. A partial-commit        writes, commit on success
                                      for every         scenario was not reproduced.        and roll back on
                                      response,                                             exceptions. Add a
                                      including error                                       failure-path test.
                                      responses.                                            

  6              `app.py:74–88`       Numeric           Yes --- `float()` accepts strings   **COMPLETE** --- reject
                                      validation        such as `nan` and `inf`; there is   non-finite values (for
                                      accepts NaN and   no finite-number check.             example, with
                                      infinity.                                             `math.isfinite`) and test
                                                                                            NaN, positive/negative
                                                                                            infinity and ordinary
                                                                                            numbers.

  7              `app.py:131–136`     PMO tracking      Yes --- `can_track` grants access   **TO DO** --- align the
                                      permission is not to any user whose group is `pmo`,   permission condition with
                                      restricted by     regardless of status. README says   the documented workflow;
                                      investment        owners or PMO can record            test PMO access for Draft,
                                      status.           measurements/reviews after          In approval, Approved and
                                                        approval.                           Rejected investments.

  8              `app.py:1017–1022`   Submission checks Yes --- the route checks record     **TO DO** --- define the
                                      only whether at   existence only. A zero-valued cost  minimum valid business-case
                                      least one metric, row would still satisfy the         data and validate the
                                      phase and cost    existence check.                    actual fields, not just row
                                      row exists. It                                        existence.
                                      does not validate                                     
                                      that those                                            
                                      records are                                           
                                      substantively                                         
                                      complete.                                             

  9              `app.py:1055–1083`   An approval       Yes --- the decision updates        **TO DO** --- make the
                                      decision writes   approval data, history, audit and   decision and all related
                                      to several        investment state; final approval    writes atomic; test
                                      related           may also create review rows. The    rollback if one write
                                      tables/records    current commit is delegated to the  fails.
                                      without an        response hook.                      
                                      explicit                                              
                                      transaction                                           
                                      boundary in the                                       
                                      route.                                                

  10             `app.py:127–137`,    The demo role     Yes --- the role switcher is        **LEAVING** for the
                 `302–310`            switcher allows   implemented in the application.     fictional-data local PoC.
                                      the browser       However, README explicitly          Replace with real
                                      session to select documents it as a demo feature and  authentication and
                                      another seeded    says real authentication is out of  server-enforced
                                      user, including   scope.                              authorisation before any
                                      privileged                                            real or hosted use.
                                      approvers. This                                       
                                      is not genuine                                        
                                      authentication.                                       

  11             `templates/*.html`   No CSRF tokens or Yes --- POST forms exist and no     **LEAVING** only while this
                 POST forms; `app.py` CSRF protection   CSRF token/middleware was found in  remains an isolated local
                 POST routes          mechanism were    the supplied source. No CSRF        demo. Add CSRF protection
                                      found for         exploit was demonstrated.           before hosted or
                                      state-changing                                        authenticated use.
                                      POST forms.                                           
  ---------------------------------------------------------------------------------------------------------------------

## What I fixed, and why


### Finding #3: input length validation

Server-side maximum lengths are now enforced for the investment name (120
characters) and description (2000 characters) in both the overview save
route and the create new investment route. Over-limit values are rejected
with an error message and nothing is saved. Matching `maxlength` attributes
were added to both forms, but the server check is the real protection
because browser-side limits can be bypassed.

**Files/functions changed:** `app.py` (`MAX_NAME_LEN`, `MAX_DESC_LEN`,
`check_len()`, `save_overview`, `investment_new`);
`templates/inv_overview.html`; `templates/investment_new.html`.

-   Verification: Name tested at 120 characters (saved) and 121
    (rejected). Description tested at 2000 (saved) and 2001 (rejected).
    Both the Overview edit form and the Create new investment form were
    tested, with `maxlength` removed in the browser so the server-side
    check was exercised. `maxlength` confirmed to stop input at the limit.
-   Commit: `a3368d5`

###  Finding #6: finite numeric validation

Update `form_num()` to reject NaN and positive/negative infinity after
parsing. These values can otherwise enter calculations that expect
ordinary finite numbers, potentially making financial and capacity
reporting unreliable. Test ordinary numbers, `nan`, `inf` and `-inf`.

-   Verification: Accepted: 1500.50, 1,250,000. Rejected with ‘must be a number’: nan, inf, -inf, 1e999.
-   Commit: `9672263`

### Other fixes completed

-   Finding number: `[ ]`
-   Files/functions changed: `[ ]`
-   What changed and why: `[two or three sentences]`
-   Verification: `[test and result]`
-   Commit: `[actual hash]`

## What I am knowingly leaving, and why


### Finding #1 --- SQL string concatenation

The audit query appends fixed SQL fragments to build optional filters,
but user-provided filter values are supplied separately through query
parameters. I found no evidence that the submitted values are
interpolated into executable SQL, so I am not treating this as a
demonstrated SQL injection vulnerability.

### Finding #2 --- Hardcoded fallback secret

The application uses a known fallback secret if `SECRET_KEY` is not
configured. I am leaving this only because the README describes a local
proof of concept with fictional data and no hosted deployment. It must
be replaced before deployment; a known fallback secret is not suitable
for production.

### Finding #4 --- Debug mode

Debug mode is enabled for the direct local run command. I am leaving it
for local development convenience only. It must be disabled in a
deployed environment.

### Finding #10 --- Demo role switching

The role switcher is intentionally included to demonstrate the
five-stage approval process using sample users. The README explicitly
says real authentication is out of scope. I am leaving it for the local
demonstration, not accepting it as production authentication or
authorisation.

### Finding #11 --- CSRF protection

The forms do not include visible CSRF protection. I am leaving this only
while the application remains a local, fictional-data demonstration.
CSRF protection should be added before the application is hosted or used
with authenticated accounts.

## What the reviewer got wrong

### SQL injection was not demonstrated

The reviewer could flag the `sql +=` pattern as worth inspecting, but
string concatenation alone does not prove SQL injection. In
`app.py:1092–1105`, the query adds fixed SQL fragments while user values
are passed through the parameter list. I therefore classify this as a
review point, not a confirmed injection vulnerability.

There is also an f-string SQL statement at `app.py:574`, but the
interpolated column name comes from a fixed tuple of allowed field
names; the submitted value is still parameterised. This is not evidence
of an exploitable user-controlled SQL injection.

### Authentication finding needs the proof-of-concept context

The role switcher really does allow selection of seeded users and
privileged roles, but the README explicitly describes this as a
demonstration feature and states that real authentication is out of
scope. The reviewer should identify it as a production-readiness
limitation rather than imply that the implementation violates its stated
local-demo scope.

### CSRF severity needs context

The absence of CSRF protection is real: there are state-changing POST
forms and no visible CSRF mechanism. However, the README describes a
local proof of concept with no real authentication or hosted deployment.
The issue should be documented as a deployment prerequisite, not
described as an exploit that was actually carried out.

### Financial-year validation was not shown to be defective

The README specifies calendar financial years, and the application
stores a financial-year integer. The earlier review did not demonstrate
a specific inconsistency with that convention, so I would not include it
as a confirmed defect.

### Missing cascading deletes were not shown to be a functional defect

The schema generally does not specify `ON DELETE CASCADE`, but the
review did not establish a general parent-record deletion requirement or
demonstrate a failing deletion workflow. This is a design consideration,
not a proven application bug.

### No SQL injection or other exploit was reproduced

This review was static inspection. The numeric, transaction, CSRF and
permission findings are supported by code paths, but no exploit,
partial-commit failure or runtime error was reproduced. They should be
described as code-supported findings until verified with tests.

------------------------------------------------------------------------

