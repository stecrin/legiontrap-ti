⏺ LegionTrap — In Plain English

  A scene to start with

  Imagine you have a server connected to the internet. From the moment it goes online, strangers start knocking on its door. Not metaphorically — literally,
  every few seconds, automated systems somewhere in the world try to log in, probe its services, guess passwords, look for weaknesses. Most fail. Some are
  clumsy. A few are sophisticated. They come from everywhere, all the time, forever.

  You would like to know who is behind these attempts, whether the same groups keep coming back, what they want, and what they will probably do next.

  Almost nothing in commercially available security tooling actually answers those questions. LegionTrap is an attempt to.

  ---
  What is LegionTrap?

  LegionTrap is a software platform that turns raw attack data into structured intelligence about who is attacking you and how they behave.

  It does not protect a network by itself. It is not a firewall, antivirus, or intrusion detection system. It is the layer that sits behind those tools and
  tries to make sense of what they see — specifically the part of "what they see" that comes from honeypots.

  A honeypot is a deliberately exposed system designed to look like a real target. Anyone who connects to it is, by definition, doing something they shouldn't
   — there is no legitimate reason for a honeypot to receive traffic. Security researchers run honeypots specifically to study attacker behavior in a safe,
  contained way. LegionTrap reads everything a honeypot sees and builds a long-term, structured memory of the activity.

  That's the platform in one paragraph: it watches the attackers attacking the bait, and remembers.

  ---
  Why was it built?

  Because the dominant model of cybersecurity intelligence is breaking.

  For decades, the standard approach has been to keep lists of bad things. Bad IP addresses. Bad domain names. Bad file signatures. Bad email senders.
  Security vendors maintain these lists, sell them as subscriptions, and security tools consult them — "is this address on the bad list? Yes? Block it."

  This works until the attacker changes the bad thing. And the cost of changing has collapsed.

  A new domain name costs a few dollars. A new server in a different country takes minutes to spin up. A new IP address is essentially free. AI tooling now
  lets attackers generate plausible-looking domains, infrastructure, and even attack scripts at industrial scale. The half-life of any given "bad IP" or "bad
  domain" — how long it stays useful as intelligence — is getting shorter every year.

  The defender is on a treadmill. Block the IP. The attacker rotates. Block the next IP. The attacker rotates again. The list-based model has a structural
  problem: it tracks things that are cheap to change.

  LegionTrap was built on a different premise: track the things that are expensive to change.

  ---
  What problem does it solve?

  Here is the core insight, in everyday terms.

  Imagine you're trying to identify a burglar who keeps hitting houses in your neighborhood. The traditional approach is to write down their license plate.
  That works once. Then they get a new car, and the license plate is useless.

  The alternative is to describe how they operate. They prefer corner houses. They come between 2 and 3 in the morning. They pick locks with a specific
  technique. They cut the alarm wire in a specific way. They take electronics but ignore jewelry.

  If you have a description like that, it doesn't matter what car they drive next time. The behavior identifies them.

  This is what LegionTrap does with attackers. It builds the behavioral description. Not the license plate.

  Specifically, it tracks five categories of behavior for every attacker it observes:

  1. Timing. When do they show up? At what rhythm? Random bursts, steady hourly probes, business hours, midnight only?
  2. Sequence. In what order do they try things? Some attackers always test SSH before web ports. Some scan in alphabetical order. Some have signature
  patterns.
  3. Protocol behavior. What tools and versions are they using? How do they negotiate connections? What handshake quirks do they have?
  4. Credentials. What usernames and passwords do they try? In what order? With what dictionaries?
  5. Targets. Which of your services do they consistently come back to? Which do they ignore?

  The combination of these five — what LegionTrap internally calls a behavioral fingerprint — is much harder to change than any IP address or domain. It
  reflects the attacker's actual operational habits, the tools they have invested in, the muscle memory of how they work. Even when they rotate everything
  else, these patterns tend to persist.

  That is the problem LegionTrap solves: it produces intelligence that doesn't expire the moment the attacker changes hosting providers.

  ---
  What happens when an attack enters the system?

  Step by step, in concrete terms:

  1. The honeypot sees something. An attacker, somewhere in the world, connects to a honeypot. They try to log in. They probe a port. They run a script. The
  honeypot logs everything they did.
  2. The honeypot sends the event to LegionTrap. Over the internet, securely, with an API key.
  3. LegionTrap records it. It stores the raw record, then enriches it: which country is the attacker coming from, which internet service provider, which
  network. This is the only part where it uses outside data — geographic and network ownership lookups.
  4. LegionTrap updates the attacker's behavioral fingerprint. Every event from this source contributes to a behavioral profile. The more events, the sharper
  the profile.
  5. LegionTrap compares this fingerprint to known campaigns. Has this kind of behavior shown up before? If yes, this activity is added to that existing
  campaign. If it's close to a known campaign but not quite a match, it is flagged for human review. If it's genuinely new, a new campaign is created.
  6. LegionTrap updates the long-term history. Every time the fingerprint changes — new patterns, new credentials, new targets — a snapshot is recorded. Over
  months, this builds a longitudinal record: how is this attacker evolving? Are they stabilizing or drifting?
  7. The operator sees it in the dashboard. Whoever is running LegionTrap — the operator — can browse all of this through a web interface. They can also
  export blocklists for their actual firewall, request an AI-generated written summary of a particular campaign, and link campaigns to actors they've
  identified.
  8. Nothing happens automatically. This is important. LegionTrap does not block, alert, or act on its own. It surfaces information. The operator decides what
   to do.

  That entire flow runs continuously, in the background, on whatever machine the operator has chosen to run LegionTrap on. There is no cloud service. There is
   no shared database. The intelligence belongs to the operator alone.

  ---
  What is a campaign?

  A campaign, in LegionTrap, is a coordinated stretch of activity that shares behavioral characteristics — usually spanning many source addresses and a
  meaningful period of time.

  Think of it as an outbreak in disease surveillance. You don't necessarily know everyone involved. You don't know exactly where it started. But you can see
  that this thing is happening, that it has identifiable features, that it has a start, that it sometimes goes quiet, and that it sometimes comes back.

  A campaign is what LegionTrap calls that thing. It is not a person. It is not a group. It is a coherent pattern of activity that the platform has identified
   and given a name.

  Campaigns have lifecycles. They are first active when activity is ongoing. They become dormant if activity stops. They are marked reactivated if a dormant
  campaign starts up again — which, in this kind of data, happens more than you would expect. They are marked historical if enough time passes that they're
  considered concluded. None of these labels are permanent. A historical campaign can come back. That's part of the point.

  ---
  What is an actor?

  An actor is what a campaign is not. A campaign is a pattern of activity. An actor is the entity — a person, a group, an organization, a government, a piece
  of automation — that is presumed responsible for one or more campaigns.

  The distinction matters because identifying actors is genuinely hard and often guesswork. Saying "this campaign exists" is a low-confidence claim — the data
   shows it. Saying "this campaign was conducted by Group X" is a much higher-confidence claim that requires evidence the platform cannot fully verify.

  LegionTrap handles this carefully. Actors are not created automatically. The platform may suggest that two campaigns look similar enough to potentially
  share an actor, but the suggestion is advisory only. A human operator decides whether to accept it. The platform makes it easy to track these decisions,
  link campaigns to actors explicitly, and review the evidence — but it never makes the attribution call by itself.

  This is a deliberate design choice. Attribution mistakes in cybersecurity are common and consequential. The operator stays in charge of that judgment.

  ---
  Why is behavior important?

  The IP address rotates. The domain rotates. The malware sample is regenerated by an AI tool with slight variations. The attacker's method of operating —
  when they show up, what order they try things in, what tools they prefer, how they handle errors — changes much more slowly.

  Behavior changes slowly because it reflects investment. An attacker who has spent six months refining a specific approach is not going to throw it out the
  next morning. The tools they use have learning curves. The dictionaries they use are tuned. The infrastructure layouts they prefer have reasons. Changing
  all of that costs real time and money.

  So while infrastructure-based intelligence has a half-life of days or hours, behavioral intelligence has a half-life of weeks or months. In some cases,
  years. That difference compounds: a defender who has been tracking behavior for two years has institutional memory that no commercial threat feed can sell,
  because no feed has access to that defender's specific observations.

  The longer LegionTrap runs in a given environment, the better its behavioral memory becomes. The intelligence accumulates with time. This is the opposite of
   the indicator model, where intelligence depreciates with time.

  ---
  What can LegionTrap do today?

  A focused list of what currently works:

  - Ingest events from honeypots in a standard format
  - Enrich events with geographic and network ownership information
  - Build behavioral fingerprints for every observed attacker
  - Group activity into campaigns automatically, using a deterministic similarity algorithm
  - Track campaign lifecycles through active, dormant, reactivated, and historical states
  - Detect reactivation when a dormant campaign returns
  - Record behavioral history so the platform can show how an attacker's patterns have evolved
  - Compute behavioral stability — has this campaign's tooling been steady, or is it drifting?
  - Alert on behavioral drift when stability scores cross configured thresholds
  - Surface uncertain cases for analyst review when clustering is borderline
  - Improve over time by feeding analyst review decisions back into the clustering weights
  - Create and manage actor profiles that link multiple campaigns to a presumed responsible party
  - Suggest actor attribution candidates — read-only, advisory
  - Generate firewall blocklists in standard formats, with optional privacy protections
  - Export to standard threat intelligence formats (STIX, ATT&CK Navigator) for sharing with other tools
  - Produce AI-generated narrative summaries of campaigns and threat briefs, when the operator requests them, with full audit trail
  - Display everything in a web dashboard
  - Audit every action

  It does this on a single machine, with no cloud dependency, no shared intelligence feed, and no subscription requirement.

  ---
  What can it not do yet?

  An honest list of gaps:

  - It cannot predict the future. It tells you what happened and what is happening. It does not yet forecast which dormant campaigns are likely to return,
  when a campaign's behavior is likely to cross a threshold, or what an attacker is likely to do next.
  - It cannot share intelligence with other deployments. Each LegionTrap is an island. If two operators are both being attacked by the same group, neither
  knows that the other is seeing it.
  - It cannot deploy detections to your defenses automatically. It produces blocklists, but it does not yet generate detection rules for intrusion detection
  systems, host monitors, or other defensive tooling.
  - It is built for a single operator. Multi-user workflows, role separation, team collaboration — none of that exists.
  - It assumes a single sensor type. It was designed and tested primarily with one kind of honeypot. Operators running multiple sensor types may find rough
  edges.
  - It has not been production-hardened at scale. The storage layer is designed to support migration to a heavier database, but that migration has not been
  needed and not been performed.
  - It does not pull in external threat intelligence. It builds intelligence from your own observations only. Integration with outside data sources is not
  part of the current platform.

  These are not embarrassments. They are choices about what to build first and what to build later.

  ---
  Why is it different from traditional security tools?

  Traditional threat intelligence platforms tend to share three properties: they are indicator-based (centered on bad IPs, domains, file hashes), they are
  externally curated (a vendor decides what's bad), and they are generic (the same intelligence is sold to everyone).

  LegionTrap inverts all three.

  It is behavior-based. What it remembers about an attacker is not the address they came from but how they operated when they got there.

  It is locally built. No vendor curates this data. The operator's own observations are the only source of truth. There is no opinion that has been filtered
  through someone else's business model.

  It is specific to one operator's exposure. Two LegionTrap deployments running in different environments will, over time, develop completely different
  intelligence — because they are seeing different attackers attacking different targets. This is not a bug. It is the entire point. Generic intelligence
  about everyone's attackers is less useful than specific intelligence about your own.

  It is also different in a less obvious way: it is deliberately conservative about AI. The AI layer in LegionTrap reads structured, deterministic data and
  produces written summaries on operator request. It does not make decisions. It does not categorize campaigns. It does not assign attribution. Every
  conclusion the platform draws is reachable through a transparent, repeatable calculation that an operator can audit. AI is a writer. It is not a judge.

  This stands in contrast to a growing tendency in the industry to put machine learning models at the center of decision-making, where neither the operator
  nor the vendor can fully explain why a particular threat was flagged.

  ---
  What is the long-term vision?

  The long-term thesis has three layers.

  Layer one: behavioral intelligence compounds. A LegionTrap deployment that has been running for one year is meaningfully more valuable than one running for
  six months. After two or three years, the institutional memory it has accumulated — about specific attackers, their evolution, their dormancy and
  reactivation patterns — becomes something no commercial product can replicate. The platform gets better just by continuing to run.

  Layer two: prediction. Eventually, this longitudinal data should support forecasting. Which dormant campaigns are likely to come back, and when? Which
  active campaigns are about to drift, and where? These predictions are not yet built, but the data structures that will make them possible are already
  accumulating. The platform is being built such that the predictive layer can be added when there is enough history to justify it.

  Layer three: federation. In the longer term, multiple operators running LegionTrap could share behavioral patterns with each other — not raw data, not
  source addresses, just the behavioral signature — so that an attacker first observed by operator A is recognized faster when they show up at operator B.
  This is harder than it sounds. It requires trust models, quality controls, and incentive structures that don't exist yet. It is a real long-term direction
  but explicitly not the next step.

  Underneath all three layers is a single belief: that as AI accelerates the rate at which traditional indicators (IPs, domains, hashes) lose their value,
  behavioral intelligence becomes the only kind that holds up. LegionTrap is a bet on that future.

  ---
  The three explanations

  One sentence: LegionTrap is a software platform that watches attackers hitting honeypot servers, records how each attacker operates, and builds long-term
  intelligence about who is attacking — based on behavior patterns instead of throwaway IP addresses or domain names.

  Thirty seconds: Most cybersecurity intelligence is organized around indicators — IP addresses, domain names, file fingerprints — which attackers can rotate
  in minutes for almost no money. That makes traditional intelligence stale almost as fast as it's produced. LegionTrap takes a different approach: it watches
   attackers hitting honeypots and records how they operate — their timing patterns, the order they probe things, the credentials they try, the targets they
  prefer. That kind of behavioral information is much harder for attackers to change, so it stays useful much longer. Over months and years, a LegionTrap
  deployment builds a long-term behavioral memory of its specific attackers, which a defender can use to recognize them across infrastructure changes.
  Everything runs locally — there is no cloud service, no shared feed, no vendor. The operator owns the data, the analysis, and the conclusions.

  Two minutes: LegionTrap is a self-hosted intelligence platform for honeypot operators. A honeypot is a deliberately exposed fake server whose only purpose
  is to attract attackers so they can be studied safely. LegionTrap takes everything a honeypot sees and turns it into structured, long-term intelligence.

  The platform was built because the dominant model of threat intelligence is breaking down. Most security tools rely on lists of bad IP addresses, bad domain
   names, and bad file signatures. These lists go stale fast because attackers can change all of those things cheaply — and AI tooling is making the change
  cheaper every year. Defenders end up on a treadmill of blocking what's already been rotated away.

  LegionTrap tracks behavior instead. For every attacker it sees, it builds a profile across five dimensions: when they show up, in what order they try
  things, which tools they use, what credentials they try, and which targets they consistently come back to. The combination is what the platform calls a
  behavioral fingerprint. Behavioral fingerprints change much more slowly than infrastructure because they reflect the attacker's actual operational habits —
  habits that take real time and effort to change. So while a list of bad IPs goes stale in days, a behavioral fingerprint stays useful for months or years.

  When events come in, LegionTrap groups related activity into campaigns. Campaigns have lifecycles: they are active, then dormant, sometimes reactivated,
  eventually marked historical. Operators can also create actor profiles — people, groups, or organizations they believe are responsible for one or more
  campaigns. The platform suggests possible matches but never makes attribution decisions automatically. The operator stays in charge of every consequential
  The three explanations

  One sentence: LegionTrap is a software platform that watches attackers hitting honeypot servers, records how each attacker operates, and builds long-term
  intelligence about who is attacking — based on behavior patterns instead of throwaway IP addresses or domain names.

  Thirty seconds: Most cybersecurity intelligence is organized around indicators — IP addresses, domain names, file fingerprints — which attackers can rotate
  in minutes for almost no money. That makes traditional intelligence stale almost as fast as it's produced. LegionTrap takes a different approach: it watches
   attackers hitting honeypots and records how they operate — their timing patterns, the order they probe things, the credentials they try, the targets they
  prefer. That kind of behavioral information is much harder for attackers to change, so it stays useful much longer. Over months and years, a LegionTrap
  deployment builds a long-term behavioral memory of its specific attackers, which a defender can use to recognize them across infrastructure changes.
  Everything runs locally — there is no cloud service, no shared feed, no vendor. The operator owns the data, the analysis, and the conclusions.

  Two minutes: LegionTrap is a self-hosted intelligence platform for honeypot operators. A honeypot is a deliberately exposed fake server whose only purpose
  is to attract attackers so they can be studied safely. LegionTrap takes everything a honeypot sees and turns it into structured, long-term intelligence.

  The platform was built because the dominant model of threat intelligence is breaking down. Most security tools rely on lists of bad IP addresses, bad domain
   names, and bad file signatures. These lists go stale fast because attackers can change all of those things cheaply — and AI tooling is making the change
  cheaper every year. Defenders end up on a treadmill of blocking what's already been rotated away.

  LegionTrap tracks behavior instead. For every attacker it sees, it builds a profile across five dimensions: when they show up, in what order they try
  things, which tools they use, what credentials they try, and which targets they consistently come back to. The combination is what the platform calls a
  behavioral fingerprint. Behavioral fingerprints change much more slowly than infrastructure because they reflect the attacker's actual operational habits —
  habits that take real time and effort to change. So while a list of bad IPs goes stale in days, a behavioral fingerprint stays useful for months or years.

  When events come in, LegionTrap groups related activity into campaigns. Campaigns have lifecycles: they are active, then dormant, sometimes reactivated,
  eventually marked historical. Operators can also create actor profiles — people, groups, or organizations they believe are responsible for one or more
  campaigns. The platform suggests possible matches but never makes attribution decisions automatically. The operator stays in charge of every consequential
  judgment.

  What LegionTrap can do today: ingest events, build fingerprints, identify campaigns, track lifecycle changes, detect reactivations, surface behavioral
  drift, manage actor attribution, generate firewall blocklists, export to standard intelligence formats, and produce AI-written summaries on demand with a
  full audit trail. What it does not do yet: predict future activity, share intelligence with other deployments, generate detection rules automatically for
  non-firewall defenses, or support multi-user workflows.

  The long-term direction is predictive intelligence built on the longitudinal data the platform accumulates, and eventually federated behavioral pattern
  sharing between consenting operators. The deeper bet is that as traditional indicator-based intelligence becomes cheaper to defeat, behavioral intelligence
  becomes the only kind that holds up.
