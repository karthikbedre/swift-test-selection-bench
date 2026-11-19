// index-query: given changed declarations, list every file whose code refers to them,
// according to the compiler's index store.
//
// Reads one JSON request on stdin and writes one JSON response on stdout. The Python
// compiler-index selector builds the request; see tsel/selectors/compiler_index.py.
//
// Request:
//   {
//     "store": "<index store dir>", "database": "<scratch dir for the db>",
//     "library": "<path to libIndexStore.dylib or .so>",
//     "changes": [{"path": "/abs/File.swift", "startLine": 10, "endLine": 14, "mode": "range"}],
//     "addedNames": ["newOverloadName"],
//     "maxDepth": 50
//   }
//   mode "range": every definition whose name sits on a line in [startLine, endLine].
//   mode "nearest": the last definition at or above startLine (used when the line range
//   could not be mapped to a declaration).
//
// Response:
//   {"resolved": [...], "unresolved": [...], "files": {"/abs/path.swift": "ModuleName"},
//    "seedSymbols": n, "visitedSymbols": n}

import Foundation
import IndexStoreDB

struct Change: Codable {
    let path: String
    let startLine: Int
    let endLine: Int
    let mode: String?
}

struct Request: Decodable {
    let store: String
    let database: String
    let library: String
    let changes: [Change]
    let addedNames: [String]
    let maxDepth: Int?
}

struct Resolved: Encodable {
    let path: String
    let startLine: Int
    let symbols: [String]
}

struct Response: Encodable {
    var resolved: [Resolved] = []
    var unresolved: [Change] = []
    var files: [String: String] = [:]
    var seedSymbols = 0
    var visitedSymbols = 0
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

let input = FileHandle.standardInput.readDataToEndOfFile()
let request: Request
do {
    request = try JSONDecoder().decode(Request.self, from: input)
} catch {
    fail("index-query: cannot read request: \(error)")
}

let db: IndexStoreDB
do {
    let library = try IndexStoreLibrary(dylibPath: request.library)
    db = try IndexStoreDB(
        storePath: request.store,
        databasePath: request.database,
        library: library,
        waitUntilDoneInitializing: true,
        listenToUnitEvents: false
    )
    db.pollForUnitChangesAndWait(isInitialScan: true)
} catch {
    fail("index-query: cannot open index store: \(error)")
}

var response = Response()
var moduleOf: [String: String] = [:]   // symbol USR -> module that defines it
var seeds = Set<String>()

/// Definitions in one file. Uses `symbols(inFilePath:)`, which every indexstore-db release branch has.
func definitions(inFile path: String) -> [SymbolOccurrence] {
    var out: [SymbolOccurrence] = []
    for symbol in db.symbols(inFilePath: path) {
        out += db.occurrences(ofUSR: symbol.usr, roles: .definition).filter {
            $0.location.path == path && !$0.roles.contains(.implicit) && !$0.location.isSystem
        }
    }
    return out
}

/// The property behind an accessor, so that callers of the property are found.
func owningProperty(of usr: String) -> [String] {
    db.occurrences(ofUSR: usr, roles: .definition).flatMap { occ in
        occ.relations.filter { $0.roles.contains(.accessorOf) }.map { $0.symbol.usr }
    }
}

/// Protocol requirements a symbol satisfies and declarations that override or satisfy it.
func overrideFamily(of usr: String) -> [String] {
    var out: [String] = []
    for occ in db.occurrences(ofUSR: usr, roles: .definition) {
        out += occ.relations.filter { $0.roles.contains(.overrideOf) }.map { $0.symbol.usr }
    }
    out += db.occurrences(relatedToUSR: usr, roles: .overrideOf).map { $0.symbol.usr }
    return out
}

func addSeed(_ usr: String, module: String) {
    if seeds.insert(usr).inserted {
        moduleOf[usr] = module
    }
}

// 1. Changed declarations that exist in the indexed (base) revision.
for change in request.changes {
    let defs = definitions(inFile: change.path)
    var hits: [SymbolOccurrence]
    if change.mode == "nearest" {
        hits = defs.filter { $0.location.line <= change.startLine }
            .max(by: { $0.location.line < $1.location.line }).map { [$0] } ?? []
    } else {
        hits = defs.filter { $0.location.line >= change.startLine && $0.location.line <= change.endLine }
    }
    if hits.isEmpty {
        response.unresolved.append(change)
        continue
    }
    for hit in hits {
        addSeed(hit.symbol.usr, module: hit.location.moduleName)
    }
    response.resolved.append(Resolved(path: change.path, startLine: change.startLine,
                                      symbols: hits.map { $0.symbol.name }))
}

// 2. Declarations added at head: existing symbols with the same base name may lose overload resolution.
for name in request.addedNames {
    let matches = db.canonicalOccurrences(containing: name, anchorStart: true, anchorEnd: false,
                                          subsequence: false, ignoreCase: false)
    for occ in matches where occ.symbol.name == name || occ.symbol.name.hasPrefix(name + "(") {
        if !occ.location.isSystem {
            addSeed(occ.symbol.usr, module: occ.location.moduleName)
        }
    }
}

for usr in Array(seeds) {
    for related in overrideFamily(of: usr) {
        addSeed(related, module: moduleOf[usr] ?? "")
    }
}
response.seedSymbols = seeds.count

// 3. References, followed inside the defining module to the declarations that contain them.
var visited = seeds
var frontier = Array(seeds)
var depth = 0
let maxDepth = request.maxDepth ?? 50
let referenceRoles: SymbolRole = [.reference, .call, .read, .write, .definition, .declaration]

while !frontier.isEmpty && depth < maxDepth {
    var next: [String] = []
    for usr in frontier {
        let home = moduleOf[usr]
        for occ in db.occurrences(ofUSR: usr, roles: referenceRoles) where !occ.location.isSystem {
            response.files[occ.location.path] = occ.location.moduleName
            guard occ.location.moduleName == home, !occ.roles.contains(.definition) else { continue }
            for rel in occ.relations where rel.roles.contains(.calledBy) || rel.roles.contains(.containedBy) {
                var containers = [rel.symbol.usr]
                containers += owningProperty(of: rel.symbol.usr)
                for container in containers where visited.insert(container).inserted {
                    moduleOf[container] = home
                    next.append(container)
                    for related in overrideFamily(of: container) where visited.insert(related).inserted {
                        moduleOf[related] = home
                        next.append(related)
                    }
                }
            }
        }
    }
    frontier = next
    depth += 1
}
response.visitedSymbols = visited.count

let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]
do {
    FileHandle.standardOutput.write(try encoder.encode(response))
} catch {
    fail("index-query: cannot write response: \(error)")
}
