import Words

let name = CommandLine.arguments.dropFirst().first ?? "world"
print("Hello, \(name)!")
