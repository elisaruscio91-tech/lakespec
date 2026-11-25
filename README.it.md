# lakespec

**Un contratto. Da lì escono pipeline, catalogo e contesto per gli agenti.**

lakespec compila un contratto dati [ODCS](https://bitol.io) più un modello
semantico [OSI](https://ossie.apache.org) in ciò che il
tuo lakehouse esegue davvero — e nel contesto governato che leggono i tuoi
agenti AI. Apache-2.0, self-hosted, nessun account richiesto.

```bash
pip install -e ".[duckdb,dev]"
lakespec compile examples/retail/semantics/sales.osi.yaml --adapter duckdb --out out/
```

Gira su un portatile in meno di un minuto. Niente cluster, niente cloud,
nessuna credenziale.

## Il problema

In uno stack normale il *significato* del dato vive in tre posti: le
trasformazioni in dbt o Spark, la documentazione nel catalogo, e il contesto che
serve a un agente per rispondere bene da nessuna parte. Divergono la settimana
dopo averli scritti. Poi qualcuno ridefinisce "fatturato" escludendo l'IVA, lo
schema non cambia di una virgola, e ogni dashboard inizia a mentire.

lakespec rende quei tre artefatti **output di un solo input**. Non c'è niente da
tenere sincronizzato perché c'è una cosa sola.

## Cosa lakespec non è

- **Non è una piattaforma.** È un compilatore: nessun runtime, nessuno
  scheduler, nessuna interfaccia, nessuno storage. Emette file che esegui dove
  già esegui le cose.
- **Non è un formato nuovo.** ODCS è uno standard della Linux Foundation
  valutato *Adopt* sul Technology Radar di Thoughtworks; OSI (ora Apache Ossie, in incubazione) è alla Apache
  Foundation con Snowflake, dbt Labs, Salesforce, Google e Databricks nel
  working group. Inventare un formato sarebbe il modo più rapido di rendere
  tutto questo non adottabile.
- **Non è un costruttore grafico di pipeline.** Una pipeline disegnata col mouse
  non si diffa, non si revisiona, non si testa. Qui il foglio Excel è una
  *superficie di editing*; la verità è lo YAML in git.

## Le decisioni di design che contano

**L'agente non scrive SQL.** `lakespec context` emette un vocabolario chiuso:
tabelle, colonne visibili, metriche, sinonimi, percorsi di join dichiarati,
istruzioni. Il livello in linguaggio naturale restituisce una *query semantica* —
metrica, dimensioni, filtri, grana — e il compilatore genera lo SQL dalle
definizioni dichiarate.

Non è prudenza, è correttezza: il percorso di join viene dal contratto e non da
un'ipotesi, l'aggregazione viene dalla definizione della metrica, il fan-out che
raddoppia i conteggi diventa rilevabile invece che silenzioso, e la stessa
domanda produce sempre lo stesso SQL. E poiché l'insieme di scelte è chiuso,
**basta un modello piccolo a pesi aperti**: è ciò che rende possibile un
deployment interamente on-premise, con nessun dato che esce dall'azienda.

**L'agente propone, l'umano ratifica.** L'output di un agente è una pull
request, mai un contratto in produzione. Il contratto è l'unica cosa che rende
affidabile tutto il resto: se è lui stesso probabilistico, hai solo spostato
l'allucinazione un livello più in alto e le hai dato autorità. Profilazione
deterministica per tipi, null e chiavi candidate; LLM solo per la prosa e per
*citare* le definizioni autorevoli; `classification`, `primaryKey` e le
definizioni delle metriche solo a mano.

**Lo schema evolution è classificato, non scoperto in produzione.** Quattro
categorie: `backward`, `forward`, `breaking` e `semantic` — quest'ultima è
quella che nessun type system vede, quando nome e tipo restano identici e il
significato cambia. Un bronze permissivo registra lo schema osservato, le
colonne nuove atterrano ma restano **in quarantena** finché non entrano nel
contratto, e le modifiche breaking falliscono subito.

## Il report di conflitti

La documentazione aziendale su SharePoint è vecchia e si contraddice. Quindi il
flusso non è *documento → contratto*, è **documento + realtà profilata → report
di conflitti**:

> il dizionario dei dati dice che `customer_id` è numerico; la colonna reale è
> varchar con il 3% di valori non numerici

Quel report è un deliverable a sé, vendibile prima che esista il resto.

## Documentazione

La documentazione tecnica completa è in inglese, perché è lì che vivono i
contributori e i working group degli standard:

- [README.md](README.md) — panoramica completa
- [docs/architecture.md](docs/architecture.md) — i tre strati e perché i confini stanno lì
- [docs/mapping-excel-odcs-osi.md](docs/mapping-excel-odcs-osi.md) — ogni colonna del workbook alla sua chiave standard
- [docs/compatibility.md](docs/compatibility.md) — la tassonomia delle modifiche come tabella di decisione
- [docs/agents.md](docs/agents.md) — cosa un agente può e non può scrivere

## Stato

Pre-alpha, deliberatamente **spec-first**. Esiste la specifica, un esempio
completo e funzionante, la tassonomia di compatibilità, le regole per gli agenti
e l'interfaccia degli adapter: le cose su cui vale la pena litigare prima di
investire mesi in codice.

Se pensi che la mappatura sia sbagliata, [dillo](../../issues). Questa fase
serve esattamente a questo.

## Licenza

Apache-2.0, come ODCS e OSI. I tuoi contratti restano tuoi e funzionano anche
fuori da questo strumento: è tutto il punto.
