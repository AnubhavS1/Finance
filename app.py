import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    id = session["user_id"]
    # Select each stock the user has
    portfolio = db.execute("SELECT stock, shares FROM portfolio WHERE id=:id", id=id)
    grandTotal = 0
    # update grandTotal, total, and symbol prices for stocks held
    for symbol in portfolio:
        shares = symbol["shares"]
        sym = symbol["stock"]
        stock = lookup(sym)
        total = shares * stock["price"]
        grandTotal += total
        db.execute("UPDATE portfolio SET PPS=:pps, Total=:total WHERE id=:id AND stock=:symbol AND shares=:shares",
                    pps=usd(stock["price"]), total=total, id=id, symbol=symbol["stock"], shares=shares)
    # Add grandTotal to users existing cash
    cash = db.execute("SELECT cash FROM users WHERE id=:id", id=id)
    grandTotal += cash[0]['cash']
    # Render index.html with stocks=transactions table, cash=cash, total=grandTotal
    transactions = db.execute("SELECT * from portfolio WHERE id=:id", id=id)

    return render_template("index.html", transactions=transactions, cash=usd(cash[0]['cash']), total=usd(grandTotal))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("Error: Invalid symbol")
        try:
            shares = int(request.form.get("shares"))
            if not shares or shares < 0:
                return apology("Error: Invalid shares")
        except:
            return apology("Error: Invalid shares")
        # Look up stock price, get total price of transaction

        price = stock['price'] * int(request.form.get("shares"))

        usrID = session["user_id"]
        # Get user's total cash
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=usrID)
        # Go forward with transaction only if user has enough cash

        if (cash[0]['cash'] > price):
            #price = usd(price)
            # determine if user already owns shares of the stock, update portfolio
            usrSym = db.execute("SELECT shares FROM portfolio WHERE id=:id AND stock=:symbol",
                            id=usrID, symbol=stock["symbol"])
            if not usrSym:
                db.execute("INSERT INTO portfolio (id, stock, shares, PPS, total) VALUES (:id, :stock, :shares, :pps, :total)",
                           id=usrID, stock=request.form.get("symbol"), shares=request.form.get("shares"), pps=stock.get('price'), total=price)
            else:

                db.execute("UPDATE portfolio SET shares=shares + :added WHERE id=:id AND stock=:symbol",
                            added=usrSym[0]["shares"], id=usrID, symbol=lookup(request.form.get("symbol"))["symbol"])
            # Record transaction
            db.execute("INSERT INTO transactions (id, stock, shares, price_per_stock, Total) VALUES(:id, :stock, :shares, :pps, :total)"
                        , id=usrID, stock=request.form.get("symbol"), shares=request.form.get("shares"), pps=stock.get('price'), total=price)
            # Update user's total cash: cash - price
            db.execute("UPDATE users SET cash = cash - :cost WHERE id=:id", cost=price, id=usrID)
        else:
            return apology("You don't have enough money to make this transaction")
    else:
        return render_template("buy.html")
    # return index template
    return redirect(url_for("index"))


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    usrname = request.args.get("username")
    check = db.execute("SELECT * FROM users WHERE username=:username", username=usrname)

    if not check and len(usrname) > 1:
        return jsonify(True)
    else:
        return jsonify(False)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE id=:id", id=session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock=lookup(request.form.get("symbol"))
        if not stock:
            return apology("Couldn't get quote")
        if lookup(request.form.get("symbol")) == None:
            return apology("No sign")
        stock["price"] = usd(stock["price"])
        return render_template("quoted.html", quote=stock)
    else:
        return render_template("quote.html");



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        # check if user entered username, pswd, pswd again, and if they match
        if not request.form.get("username"):
            return apology("No username entered", 400)
        elif not request.form.get("password"):
            return apology("No password entered", 400)
        elif not request.form.get("confirmation"):
            return apology("Need to enter password a second time", 400)
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("Passwords do not match", 400)

        hashPswd = generate_password_hash(request.form.get("password"))
        newUsr =  db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)",
                            username = request.form.get("username"),
                            hash = hashPswd)
        # if user already exists ...
        if not newUsr:
            return apology("User already exists", 400)
        # remember user until logout
        session["user_id"] = newUsr

        return redirect("/")

    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        usrStocks = db.execute("SELECT stock, SUM(shares) as total FROM transactions WHERE id=:id GROUP BY stock HAVING total > 0",
                                id=session["user_id"])
        return render_template("sell.html", stocks=usrStocks)
    else:
        # variables
        symbol = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares"))
        usrID = session["user_id"]
        usrShares = db.execute("SELECT shares FROM portfolio WHERE id=:id AND stock=:symbol",
                                id=usrID, symbol=symbol["symbol"])
        price = symbol["price"]
        # errors
        if symbol == None:
            return apology("Error: Invalid Symbol")
        if shares < 0:
            return apology("Error: Negative number of shares entered")
        elif shares > usrShares[0]["shares"]:
            return apology("Error: Trying to sell more shares than owned")
        # insert the sale into sales table
        db.execute("INSERT INTO transactions (id, stock, shares, price_per_stock, Total) values(:id, :symbol, :shares, :price, :total)",
                    id=usrID, symbol=symbol["symbol"], shares=-shares, price=price, total=shares*price)
        # update user's cash
        db.execute("UPDATE users SET cash = cash + :sale WHERE id=:id", sale=price*shares, id=usrID)
        # update portfolio table
        #db.execute("UPDATE portfolio SET shares = shares - :usr WHERE id=:id AND stock=:symbol",
                    #usr=usrShares[0]["shares"], id=usrID, symbol=symbol["symbol"])
        # update shares of stock sold
        if usrShares[0]["shares"] - shares == 0:
            db.execute("DELETE FROM portfolio WHERE id=:id AND stock=:symbol", id=usrID, symbol=symbol["symbol"])
        else:
            db.execute("UPDATE portfolio SET shares = shares - :sold WHERE id=:id AND stock=:symbol",
                        sold=shares, id=usrID, symbol=symbol["symbol"])
        # return index
        return redirect(url_for("index"))

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
