# Hyperliquid Funding Analyzer

## Instruções para Claude

- **NÃO pedir permissão para editar arquivos** se o usuário já aceitou a sugestão ou pediu a mudança. Apenas faça o edit diretamente.

## Visão Geral

Dashboard para análise de funding rates de todos os pares perpétuos do Hyperliquid, incluindo crypto (Perps), TradFi (stocks/índices) e HIP-3.

## Arquitetura

### Stack
- **Frontend**: React 18 (via CDN, sem build)
- **Styling**: Tailwind CSS
- **Database**: Arquivos JSON no servidor (via server.py)
- **API**: Hyperliquid Public API (https://api.hyperliquid.xyz/info)

### Regra de Persistência
**IMPORTANTE**: Todas as informações devem ser salvas no banco de dados do servidor (arquivos JSON), **NUNCA** no localStorage do navegador. Isso inclui:
- Favoritos
- Blacklist de tokens
- Preferências do usuário
- Histórico de funding
- Dados de mercado

### Estrutura do Arquivo
```
hyperliquid-funding/
├── index.html          # Aplicação completa (single file)
├── start-server.bat    # Script para iniciar servidor (Windows)
├── start-server.sh     # Script para iniciar servidor (Mac/Linux)
└── CLAUDE.md           # Esta documentação
```

## Base de Dados (IndexedDB)

### Database: `HyperliquidFundingDB`

#### Stores:
1. **marketData** - Dados de mercado atuais
   - Key: `coin` (string)
   - Campos: coin, category, funding, openInterest, volume24h, markPrice, maxLeverage

2. **fundingHistory** - Histórico de funding por coin
   - Key: `coin` (string)
   - Campos: coin, history (array), lastUpdate, recordCount

3. **metadata** - Metadados do sistema
   - Key: `key` (string)
   - Usado para: marketDataLastUpdate, cacheVersion

### Classe FundingDB
Helper estático para operações no IndexedDB:
- `getMeta(key)` / `setMeta(key, value)`
- `getAllMarketData()` / `saveAllMarketData(markets)`
- `getFundingHistory(coin)` / `saveFundingHistory(coin, history)`
- `getAllFundingHistory()` / `getHistoryTimestamps()`
- `clearAll()` / `getStats()`

## API Endpoints Utilizados

### DEX Principal (Crypto)
```javascript
POST https://api.hyperliquid.xyz/info
Body: { "type": "metaAndAssetCtxs" }
// Retorna: [meta, assetCtxs] com todos os perps crypto
```

### Histórico de Funding
```javascript
POST https://api.hyperliquid.xyz/info
Body: { "type": "fundingHistory", "coin": "BTC", "startTime": 0 }
// Retorna: array de { time, fundingRate } - máx 500 por request
```

### HIP-3 DEXs (TradFi/Stocks)
```javascript
POST https://api.hyperliquid.xyz/info
Body: { "type": "perpDexs" }
// Retorna: lista de DEXs HIP-3

POST https://api.hyperliquid.xyz/info
Body: { "type": "metaAndAssetCtxs", "dex": "xyz" }
// Retorna: assets do DEX específico (nota: parâmetro é "dex", não "perpDex")

// fundingHistory FUNCIONA para HIP-3 usando o nome completo (ex: "xyz:TSLA")
```

## Categorias de Ativos

| Categoria | Descrição | Exemplos |
|-----------|-----------|----------|
| **Perps** | Crypto perpétuos (DEX principal) | BTC, ETH, SOL |
| **TradFi** | Stocks e índices via HIP-3 | TSLA, NVDA, USA500 |
| **HIP-3** | Outros ativos HIP-3 não-TradFi | Novos tokens |

### Lógica de Categorização
```javascript
// Se tem ":" no nome = HIP-3
// Se símbolo é stock conhecida = TradFi
// Senão = Perps (crypto)
```

### Filtragem de Duplicados
- Crypto no DEX principal (BTC) é mantido
- Crypto duplicado em HIP-3 (xyz:BTC, cash:BTC) é **ignorado**
- Stocks em HIP-3 (xyz:TSLA) são **incluídas**
- Nome exibido remove prefixo do DEX (xyz:TSLA → TSLA)

## Funcionalidades dos Botões

| Botão | Função | Parâmetros |
|-------|--------|------------|
| 🔄 Refresh | Atualiza dados de mercado (funding atual, OI, volume) | `fetchMarketData(true)` |
| ➕ Buscar Novos | Busca histórico só de coins sem dados | `fetchAllFundingHistories(false, true)` |
| 🔃 Atualizar Tudo | Força atualização de todos os históricos | `fetchAllFundingHistories(true, false)` |

## Métricas Calculadas

Para cada coin:
- **Funding Atual**: Último funding rate
- **APR Atual**: `funding * 24 * 365 * 100`
- **Média 24h/7d/30d/All-time**: Média dos funding rates no período
- **Períodos**: Total de registros de funding (1 período = 1 hora)

## Performance e Rate Limiting

### Configurações Atuais (conservadoras para evitar 429)
- **Batch size**: 3 coins em paralelo
- **Delay entre batches**: 500ms
- **Delay entre páginas**: 200ms

### Estimativa de Tempo
- Primeira carga completa (~200 coins): 15-20 minutos
- Atualização incremental: segundos
- Buscar só novos: depende de quantos faltam

### Rate Limiting
A API do Hyperliquid retorna **429 Too Many Requests** se fizer muitas chamadas.
Se acontecer, esperar 2-3 minutos antes de tentar novamente.

## CORS

A API do Hyperliquid pode bloquear requests diretos do browser. Sistema usa proxies de fallback:
1. Tenta direto primeiro
2. `corsproxy.io`
3. `api.allorigins.win`
4. `cors-anywhere.herokuapp.com`

## Como Rodar

### Requisito
Precisa de servidor HTTP local (IndexedDB não funciona em `file://`)

### Windows
```bash
start-server.bat
# ou
python -m http.server 8000
```

### Mac/Linux
```bash
./start-server.sh
# ou
python3 -m http.server 8000
```

### Acesso
Abrir `http://localhost:8000` no browser

## Manutenção

### Limpar Base de Dados
Botão no footer: "🗑️ Limpar Banco de Dados"

### Ver Dados no DevTools
Chrome: F12 → Application → IndexedDB → HyperliquidFundingDB

### Adicionar Novos Símbolos TradFi
Editar array `TRADFI_SYMBOLS` no início do código:
```javascript
const TRADFI_SYMBOLS = [
    'USA500', 'TSLA', 'NVDA', ...
];
```

## Troubleshooting

| Problema | Solução |
|----------|---------|
| 429 Too Many Requests | Esperar 2-3 min, API tem rate limit |
| Dados não carregam | Verificar console (F12), pode ser CORS |
| Duplicados HIP-3 | Clicar "Limpar Banco de Dados" |
| Muito lento | Normal na primeira carga, depois é rápido |
| localStorage error | Usar servidor HTTP, não abrir arquivo direto |

## Pendente / Melhorias Futuras

### Prioridade Alta
- [ ] Exportação CSV/JSON
- [ ] Gráfico de evolução do funding
- [ ] Alertas de funding extremo (oportunidades)
- [ ] Filtros avançados (por range de funding, volume mínimo)

### Prioridade Média
- [ ] Persistir preferências (ordenação, filtros)
- [ ] Indicador de idade dos dados por coin
- [ ] Comparação lado a lado de coins

### Prioridade Baixa
- [ ] Dark/Light mode toggle
- [ ] PWA (instalável)
- [ ] Notificações push

## Testar HIP-3 Manualmente

Colar no console do browser:
```javascript
// Listar DEXs HIP-3
fetch('https://api.hyperliquid.xyz/info', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ type: 'perpDexs' })
}).then(r => r.json()).then(console.log)

// Buscar assets de um DEX específico (HIP-3)
fetch('https://api.hyperliquid.xyz/info', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ type: 'metaAndAssetCtxs', dex: 'xyz' })
}).then(r => r.json()).then(console.log)
```
